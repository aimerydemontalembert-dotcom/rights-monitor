"""
intrusion_scanner.py — Scanner multi-sources de violations de droits.
Sources : JustWatch, YouTube Data API, EPG Free TV (XMLTV), EPG Pay TV.
"""

import json
import asyncio
import logging
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Literal

try:
    import httpx
except ImportError:
    httpx = None

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

from plateformes_france import is_available_in_territory, PLATEFORMES_SVOD, CHAINES_PAYTV
import db

logger = logging.getLogger(__name__)

Severite = Literal["CRITIQUE", "HAUTE", "MOYENNE"]

# Territoires → codes pays JustWatch
JUSTWATCH_LOCALES = {
    "France":    "fr",
    "Belgique":  "be",
    "Benelux":   "be",
    "Suisse":    "ch",
    "CH":        "ch",
    "Monaco":    "mc",
    "Andorre":   "ad",
    "Dom-Tom":   "fr",
}

# EPG XMLTV sources (iptv-org/epg)
EPG_SOURCES = {
    "TF1":       "https://raw.githubusercontent.com/iptv-org/epg/master/sites/tf1.fr/tf1.fr.epg.xml",
    "M6":        "https://raw.githubusercontent.com/iptv-org/epg/master/sites/m6.fr/m6.fr.epg.xml",
    "France 2":  "https://raw.githubusercontent.com/iptv-org/epg/master/sites/france.tv/france.tv_france2.epg.xml",
    "France 3":  "https://raw.githubusercontent.com/iptv-org/epg/master/sites/france.tv/france.tv_france3.epg.xml",
    "RTL9":      "https://raw.githubusercontent.com/iptv-org/epg/master/sites/rtl9.be/rtl9.be.epg.xml",
    "Canal+":    "https://raw.githubusercontent.com/iptv-org/epg/master/sites/canalplus.com/canalplus.com.epg.xml",
}


@dataclass
class Detection:
    programme: str
    plateforme: str
    territoire: str
    source: str
    url: str = None
    date_diffusion: str = None
    heure_diffusion: str = None
    saison: int = None
    episode: int = None
    score_matching: float = 100.0
    metadata: dict = field(default_factory=dict)


@dataclass
class Violation:
    detection: Detection
    deal_id: str
    severite: Severite
    type_violation: str
    description: str


def fuzzy_match(titre_recherche: str, titre_trouve: str, seuil: int = 80) -> bool:
    if fuzz is None:
        return titre_recherche.lower() in titre_trouve.lower()
    score = fuzz.token_sort_ratio(titre_recherche.lower(), titre_trouve.lower())
    return score >= seuil


# ── JustWatch ─────────────────────────────────────────────────────────────────

async def scan_justwatch(programme: str, territoire: str, chaine_autorisee: str) -> list[Detection]:
    """Cherche un programme sur JustWatch et retourne les détections hors chaine autorisée."""
    if httpx is None:
        logger.warning("httpx non installé")
        return []

    locale = JUSTWATCH_LOCALES.get(territoire, "fr")
    detections = []

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    payload = {
        "query": programme,
        "content_types": ["show", "movie"],
        "language": "fr",
        "page": 1,
        "page_size": 5,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://apis.justwatch.com/content/titles/{locale}/popular",
                json=payload,
                headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                title = item.get("title", "")
                if not fuzzy_match(programme, title):
                    continue

                for offer in item.get("offers", []):
                    provider_name = offer.get("package_short_name", "").upper()
                    monetization = offer.get("monetization_type", "").upper()

                    if monetization not in ("FLATRATE", "SUBSCRIPTION", "FREE"):
                        continue

                    if provider_name.upper() == chaine_autorisee.upper():
                        continue

                    if not is_available_in_territory(provider_name, territoire):
                        continue

                    detections.append(Detection(
                        programme=programme,
                        plateforme=provider_name,
                        territoire=territoire,
                        source="justwatch",
                        url=offer.get("urls", {}).get("standard_web"),
                        score_matching=fuzz.token_sort_ratio(programme.lower(), title.lower()) if fuzz else 90,
                        metadata={"justwatch_title": title, "monetization": monetization}
                    ))

    except Exception as e:
        logger.error(f"JustWatch error [{programme}/{territoire}]: {e}")

    return detections


# ── YouTube Data API ──────────────────────────────────────────────────────────

async def scan_youtube(programme: str, youtube_api_key: str) -> list[Detection]:
    """Cherche des uploads non officiels sur YouTube."""
    if httpx is None or not youtube_api_key:
        return []

    detections = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "q": f'"{programme}" episode',
                    "type": "video",
                    "relevanceLanguage": "fr",
                    "maxResults": 10,
                    "key": youtube_api_key,
                }
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")
                channel = snippet.get("channelTitle", "")

                if not fuzzy_match(programme, title, seuil=70):
                    continue

                # Canaux officiels connus → pas de violation
                official_keywords = ["official", "officiel", "vevo", programme.lower()[:6]]
                if any(k in channel.lower() for k in official_keywords):
                    continue

                video_id = item["id"].get("videoId", "")
                detections.append(Detection(
                    programme=programme,
                    plateforme="YouTube",
                    territoire="France",
                    source="youtube",
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    metadata={"youtube_title": title, "channel": channel}
                ))

    except Exception as e:
        logger.error(f"YouTube API error [{programme}]: {e}")

    return detections


# ── EPG Free TV (XMLTV) ───────────────────────────────────────────────────────

async def scan_epg_free(programme: str, chaines_autorisees: list[str]) -> list[Detection]:
    """Cherche un programme dans les EPG des chaînes gratuites via XMLTV."""
    if httpx is None:
        return []

    detections = []

    for chaine, url in EPG_SOURCES.items():
        if chaine in chaines_autorisees:
            continue
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                xml_text = resp.text

            for line in xml_text.split("\n"):
                if "<title>" not in line:
                    continue
                titre = line.replace("<title>", "").replace("</title>", "").strip()
                if fuzzy_match(programme, titre):
                    detections.append(Detection(
                        programme=programme,
                        plateforme=chaine,
                        territoire="France",
                        source="epg_free",
                        metadata={"epg_title": titre}
                    ))
                    break

        except Exception as e:
            logger.debug(f"EPG {chaine} error: {e}")

    return detections


# ── EPG Pay TV ────────────────────────────────────────────────────────────────

async def scan_epg_paytv(programme: str, chaines_autorisees: list[str]) -> list[Detection]:
    """Cherche un programme sur les chaînes Pay TV non autorisées."""
    detections = []
    paytv_non_autorisees = [c for c in CHAINES_PAYTV if c not in chaines_autorisees]

    # Simulation structurée — remplacer par vraies APIs Canal+/OCS/beIN
    # Canal+ : https://www.canalplus.com/api/epg/v1/
    # OCS : API non publique, nécessite scraping Playwright
    for chaine in paytv_non_autorisees:
        logger.debug(f"EPG Pay TV scan: {chaine} pour {programme} — simulation")

    return detections


# ── Moteur principal ──────────────────────────────────────────────────────────

def _determine_severity(type_violation: str, media: str) -> Severite:
    if "exclusif" in type_violation.lower():
        return "CRITIQUE"
    if media in ("SVOD", "Pay-TV"):
        return "HAUTE"
    return "MOYENNE"


async def scan_scraper(scraper: dict, youtube_api_key: str = None) -> list[Violation]:
    """Lance tous les scans pour un scraper donné et retourne les violations."""
    programme = scraper["programme"]
    chaine = scraper["chaine"]
    territoire = scraper["territoire"]
    media = scraper["media"]
    deal_id = scraper["deal_id"]

    all_detections: list[Detection] = []

    # Scans en parallèle
    tasks = [
        scan_justwatch(programme, territoire, chaine),
        scan_epg_free(programme, [chaine]),
        scan_epg_paytv(programme, [chaine]),
    ]
    if youtube_api_key:
        tasks.append(scan_youtube(programme, youtube_api_key))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Scan error: {r}")
        else:
            all_detections.extend(r)

    violations = []
    for det in all_detections:
        type_viol = f"Diffusion {media} hors contrat ({chaine} autorisé)"
        violations.append(Violation(
            detection=det,
            deal_id=deal_id,
            severite=_determine_severity(type_viol, media),
            type_violation=type_viol,
            description=(
                f"{programme} détecté sur {det.plateforme} ({det.territoire}) "
                f"— seul {chaine} est autorisé en {media}"
            )
        ))

    db.update_scraper_timestamp(scraper["id"])
    return violations


async def run_all_scrapers(youtube_api_key: str = None) -> list[Violation]:
    """Lance tous les scrapers actifs et sauvegarde les violations en base."""
    scrapers = db.list_scrapers(actif_only=True)
    logger.info(f"Démarrage scan : {len(scrapers)} scrapers actifs")

    all_violations = []
    for scraper in scrapers:
        violations = await scan_scraper(scraper, youtube_api_key)
        for v in violations:
            diff_id = db.save_diffusion({
                "scraper_id": scraper["id"],
                "deal_id": v.deal_id,
                "programme": v.detection.programme,
                "plateforme": v.detection.plateforme,
                "territoire": v.detection.territoire,
                "url": v.detection.url,
                "source": v.detection.source,
            })
            db.save_alerte({
                "diffusion_id": diff_id,
                "deal_id": v.deal_id,
                "programme": v.detection.programme,
                "severite": v.severite,
                "type_violation": v.type_violation,
                "description": v.description,
                "plateforme": v.detection.plateforme,
                "territoire": v.detection.territoire,
                "url": v.detection.url,
            })
        all_violations.extend(violations)

    logger.info(f"Scan terminé : {len(all_violations)} violations détectées")
    return all_violations


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db.init_db()
    violations = asyncio.run(run_all_scrapers())
    print(f"\n{len(violations)} violations détectées")
    for v in violations:
        print(f"  [{v.severite}] {v.description}")
