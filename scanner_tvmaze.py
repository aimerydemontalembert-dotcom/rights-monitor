"""
scanner_tvmaze.py — Détection de diffusions TV via l'API TVmaze (gratuite, officielle).
Cherche si un programme apparaît sur une chaîne non autorisée par le contrat.
"""

import asyncio
import logging
from datetime import datetime, date, timedelta

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

TVMAZE_BASE = "https://api.tvmaze.com"

# Correspondance chaînes contractuelles → noms TVmaze
CHAINES_TVMAZE = {
    "TF1":      "TF1",
    "M6":       "M6",
    "France 2": "France 2",
    "France 3": "France 3",
    "RTL9":     "RTL9",
    "Canal+":   "Canal+",
    "W9":       "W9",
    "TMC":      "TMC",
    "NT1":      "NT1",
    "6ter":     "6ter",
    "Gulli":    "Gulli",
}


async def search_show(titre: str) -> dict | None:
    """Cherche un show sur TVmaze et retourne le premier résultat pertinent."""
    if httpx is None:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{TVMAZE_BASE}/search/shows",
                params={"q": titre}
            )
            resp.raise_for_status()
            results = resp.json()

        if not results:
            return None

        for r in results:
            show = r["show"]
            show_title = show.get("name", "")
            score = fuzz.token_sort_ratio(titre.lower(), show_title.lower()) if fuzz else (90 if titre.lower() in show_title.lower() else 0)
            if score >= 75:
                return show

    except Exception as e:
        logger.error(f"TVmaze search error [{titre}]: {e}")
    return None


async def get_episodes(show_id: int) -> list[dict]:
    """Récupère tous les épisodes d'un show."""
    if httpx is None:
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{TVMAZE_BASE}/shows/{show_id}/episodes")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"TVmaze episodes error [{show_id}]: {e}")
        return []


async def get_schedule_fr(target_date: date = None) -> list[dict]:
    """Récupère le programme TV France du jour via TVmaze."""
    if httpx is None:
        return []
    if target_date is None:
        target_date = date.today()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{TVMAZE_BASE}/schedule",
                params={"country": "FR", "date": target_date.isoformat()}
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"TVmaze schedule error: {e}")
        return []


async def scan_tvmaze_programme(
    programme: str,
    chaines_autorisees: list[str],
    deal_id: str,
    media: str = "Free-TV",
    jours_retrospectifs: int = 7
) -> list[Violation]:
    """
    Cherche si un programme a été diffusé sur une chaîne non autorisée
    durant les X derniers jours.
    """
    violations = []

    show = await search_show(programme)
    if not show:
        logger.info(f"TVmaze : '{programme}' non trouvé")
        return []

    show_id = show["id"]
    show_name = show.get("name", programme)
    network = show.get("network") or {}
    network_name = network.get("name", "")

    logger.info(f"TVmaze : '{programme}' → '{show_name}' (ID {show_id}, réseau: {network_name})")

    # Vérifier les diffusions récentes via le programme TV
    for day_offset in range(jours_retrospectifs):
        scan_date = date.today() - timedelta(days=day_offset)
        schedule = await get_schedule_fr(scan_date)

        for item in schedule:
            ep = item.get("_embedded", {}).get("show") or item.get("show") or {}
            item_show_id = ep.get("id") or (item.get("_links", {}).get("show", {}).get("href", "").split("/")[-1])

            # Comparer par ID show ou par titre fuzzy
            titre_item = ep.get("name") or item.get("name", "")
            match_by_id = str(item_show_id) == str(show_id)
            match_by_title = fuzz.token_sort_ratio(programme.lower(), titre_item.lower()) >= 80 if fuzz else False

            if not (match_by_id or match_by_title):
                continue

            # Chaîne de diffusion
            channel_info = item.get("_embedded", {}).get("show", {}).get("network") or {}
            channel_name = channel_info.get("name", "") or network_name

            # Chaîne autorisée → pas de violation
            if any(auth.lower() in channel_name.lower() for auth in chaines_autorisees):
                continue

            # Chaîne non autorisée → violation
            airtime = item.get("airtime", "")
            violations.append(Violation(
                detection=Detection(
                    programme=programme,
                    plateforme=channel_name,
                    territoire="France",
                    source="tvmaze",
                    date_diffusion=scan_date.isoformat(),
                    heure_diffusion=airtime,
                    saison=item.get("season"),
                    episode=item.get("number"),
                    score_matching=90.0,
                    metadata={"tvmaze_id": show_id, "tvmaze_title": show_name}
                ),
                deal_id=deal_id,
                severite="HAUTE",
                type_violation=f"Diffusion {media} non autorisée détectée via TVmaze",
                description=(
                    f"{programme} diffusé sur {channel_name} le {scan_date.isoformat()} à {airtime} "
                    f"(chaînes autorisées : {', '.join(chaines_autorisees)})"
                )
            ))

    # Vérification réseau principal du show
    if network_name and not any(auth.lower() in network_name.lower() for auth in chaines_autorisees):
        logger.info(f"Note : réseau principal de '{show_name}' sur TVmaze = {network_name}")

    return violations


async def run_tvmaze_scan(youtube_api_key: str = None) -> list[Violation]:
    """Scan TVmaze sur tous les blocs actifs."""
    blocs = db.get_blocs_actifs()
    blocs_tv = [b for b in blocs if b["media"] in ("Free-TV", "Pay-TV")]

    logger.info(f"TVmaze scan : {len(blocs_tv)} blocs TV à surveiller")

    all_violations = []
    for bloc in blocs_tv:
        violations = await scan_tvmaze_programme(
            programme=bloc["programme"],
            chaines_autorisees=bloc["chaines"],
            deal_id=bloc["deal_id"],
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
                "source": "tvmaze",
                "date_diffusion": v.detection.date_diffusion,
                "heure_diffusion": v.detection.heure_diffusion,
                "saison": v.detection.saison,
                "episode": v.detection.episode,
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
            })
        all_violations.extend(violations)

    return all_violations


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def test():
        print("Test TVmaze — FEMMES DE LOI sur RTL9")
        violations = await scan_tvmaze_programme(
            programme="Femmes de loi",
            chaines_autorisees=["RTL9"],
            deal_id="42222",
            media="Pay-TV",
            jours_retrospectifs=30
        )
        if violations:
            for v in violations:
                print(f"[{v.severite}] {v.description}")
        else:
            print("Aucune violation détectée (ou programme non diffusé hors RTL9 ces 30 derniers jours)")

        print("\nTest TVmaze — recherche THE GUEST")
        show = await search_show("The Guest")
        if show:
            print(f"Trouvé : {show['name']} (ID {show['id']}) sur {show.get('network', {}).get('name', 'N/A')}")
        else:
            print("Non trouvé sur TVmaze")

    asyncio.run(test())
