"""
scanner_tmdb.py — Détection de disponibilité SVOD via TMDB Watch Providers.
TMDB utilise les données JustWatch pour les plateformes de streaming par pays.
"""

import asyncio
import logging
import os
from datetime import datetime

try:
    import httpx
except ImportError:
    httpx = None

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

import db
from intrusion_scanner import Detection, Violation

logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")

# Codes pays TMDB par territoire contractuel
TERRITOIRE_TMDB = {
    "France":    "FR",
    "Dom-Tom":   "FR",
    "Belgique":  "BE",
    "Benelux":   "BE",
    "Suisse":    "CH",
    "CH":        "CH",
    "Monaco":    "MC",
    "Andorre":   "AD",
}

# Correspondance noms de plateformes TMDB → noms dans Rights Monitor
TMDB_PROVIDER_MAP = {
    "Netflix":              "Netflix",
    "Amazon Prime Video":   "Prime Video",
    "Disney Plus":          "Disney+",
    "Apple TV Plus":        "Apple TV+",
    "Canal+":               "Canal+",
    "Max":                  "Max",
    "Paramount Plus":       "Paramount+",
    "MUBI":                 "Mubi",
    "Crunchyroll":          "Crunchyroll",
    "OCS":                  "OCS",
    "Arte":                 "Arte",
    "France tv":            "France.tv",
    "Shadowz":              "Shadowz",
    "Tënk":                 "Tënk",
    "Curiosity Stream":     "Curiosity Stream",
}


async def search_title(titre: str, type_contenu: str = "multi") -> list[dict]:
    """Cherche un film ou une série sur TMDB."""
    if not TMDB_API_KEY or not httpx:
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{TMDB_BASE}/search/{type_contenu}",
                params={
                    "api_key": TMDB_API_KEY,
                    "query": titre,
                    "language": "fr-FR",
                    "page": 1,
                }
            )
            resp.raise_for_status()
            return resp.json().get("results", [])
    except Exception as e:
        logger.error(f"TMDB search error [{titre}]: {e}")
        return []


async def get_watch_providers(tmdb_id: int, media_type: str, pays: str = "FR") -> dict:
    """
    Retourne les plateformes de streaming disponibles pour un titre dans un pays.
    media_type : 'movie' ou 'tv'
    Retourne : { "flatrate": [...], "free": [...], "rent": [...], "buy": [...] }
    """
    if not TMDB_API_KEY or not httpx:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{TMDB_BASE}/{media_type}/{tmdb_id}/watch/providers",
                params={"api_key": TMDB_API_KEY}
            )
            resp.raise_for_status()
            results = resp.json().get("results", {})
            return results.get(pays, {})
    except Exception as e:
        logger.error(f"TMDB watch providers error [{tmdb_id}]: {e}")
        return {}


async def find_best_match(titre: str) -> tuple[int, str] | tuple[None, None]:
    """
    Trouve le meilleur match TMDB pour un titre.
    Retourne (tmdb_id, media_type) ou (None, None).
    """
    results = await search_title(titre, "multi")
    if not results:
        return None, None

    for r in results[:5]:
        found_title = r.get("title") or r.get("name") or ""
        media_type = r.get("media_type", "movie")
        if media_type not in ("movie", "tv"):
            continue

        score = fuzz.token_sort_ratio(titre.lower(), found_title.lower()) if fuzz else (
            90 if titre.lower() in found_title.lower() else 0
        )
        if score >= 70:
            logger.info(f"TMDB match : '{titre}' → '{found_title}' ({media_type}, score {score})")
            return r["id"], media_type

    return None, None


async def scan_tmdb_programme(
    programme: str,
    chaines_autorisees: list[str],
    deal_id: str,
    territoires: list[str],
    media: str = "SVOD",
) -> list[Violation]:
    """
    Vérifie si un programme est disponible sur des plateformes non autorisées
    dans les territoires contractuels.
    """
    violations = []

    tmdb_id, media_type = await find_best_match(programme)
    if not tmdb_id:
        logger.info(f"TMDB : '{programme}' non trouvé")
        return []

    for territoire in territoires:
        pays_code = TERRITOIRE_TMDB.get(territoire, "FR")
        providers = await get_watch_providers(tmdb_id, media_type, pays_code)

        if not providers:
            continue

        # SVOD = flatrate sur TMDB
        svod_providers = providers.get("flatrate", [])
        # AVOD = free
        avod_providers = providers.get("free", [])

        all_providers = svod_providers if media == "SVOD" else (svod_providers + avod_providers)

        for provider in all_providers:
            provider_name = provider.get("provider_name", "")
            normalized = TMDB_PROVIDER_MAP.get(provider_name, provider_name)
            provider_url = providers.get("link", "")

            # Plateforme autorisée → pas de violation
            if any(auth.lower() in normalized.lower() or auth.lower() in provider_name.lower()
                   for auth in chaines_autorisees):
                continue

            violations.append(Violation(
                detection=Detection(
                    programme=programme,
                    plateforme=normalized,
                    territoire=territoire,
                    source="tmdb",
                    url=provider_url,
                    score_matching=90.0,
                    metadata={
                        "tmdb_id": tmdb_id,
                        "media_type": media_type,
                        "provider_id": provider.get("provider_id"),
                        "pays": pays_code,
                    }
                ),
                deal_id=deal_id,
                severite="CRITIQUE" if media == "SVOD" else "HAUTE",
                type_violation=f"Présence {media} non autorisée (source : TMDB/JustWatch)",
                description=(
                    f"{programme} disponible en {media} sur {normalized} ({territoire}) "
                    f"— seul(s) {', '.join(chaines_autorisees)} autorisé(s)"
                )
            ))

    return violations


async def run_tmdb_scan() -> list[Violation]:
    """Scan TMDB sur tous les blocs SVOD/AVOD actifs."""
    if not TMDB_API_KEY:
        logger.warning("TMDB_API_KEY manquante — scan ignoré")
        return []

    blocs = db.get_blocs_actifs()
    blocs_svod = [b for b in blocs if b["media"] in ("SVOD", "AVOD", "FVOD")]

    logger.info(f"TMDB scan : {len(blocs_svod)} blocs SVOD/AVOD à surveiller")

    all_violations = []
    for bloc in blocs_svod:
        violations = await scan_tmdb_programme(
            programme=bloc["programme"],
            chaines_autorisees=bloc["chaines"],
            deal_id=bloc["deal_id"],
            territoires=bloc["territoires"],
            media=bloc["media"],
        )
        for v in violations:
            diff_id = db.save_diffusion({
                "scraper_id": None,
                "deal_id": v.deal_id,
                "programme": v.detection.programme,
                "plateforme": v.detection.plateforme,
                "territoire": v.detection.territoire,
                "url": v.detection.url,
                "source": "tmdb",
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

    return all_violations


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def test():
        print("=== Test TMDB Watch Providers ===\n")

        tests = [
            ("Scab Vendor", ["EXPLORE"], "SVOD", ["France"]),
            ("She They Us", ["EXPLORE"], "SVOD", ["France"]),
            ("The Guest", ["Insomnia"], "SVOD", ["France"]),
            ("Femmes de loi", ["RTL9"], "Pay-TV", ["France"]),
        ]

        for titre, autorisees, media, territoires in tests:
            print(f"--- {titre} ---")
            tmdb_id, media_type = await find_best_match(titre)
            if tmdb_id:
                providers = await get_watch_providers(tmdb_id, media_type, "FR")
                svod = [p["provider_name"] for p in providers.get("flatrate", [])]
                print(f"  TMDB ID : {tmdb_id} ({media_type})")
                print(f"  SVOD France : {svod if svod else 'aucun'}")
                violations = await scan_tmdb_programme(titre, autorisees, "TEST", territoires, media)
                if violations:
                    for v in violations:
                        print(f"  ⚠️  [{v.severite}] {v.description}")
                else:
                    print(f"  ✅ Aucune violation détectée")
            else:
                print(f"  ❌ Non trouvé sur TMDB")
            print()

    asyncio.run(test())
