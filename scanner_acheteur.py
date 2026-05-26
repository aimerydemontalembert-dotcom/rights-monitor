"""
scanner_acheteur.py — Vue acheteur.
Détecte quand un vendeur accorde les mêmes droits exclusifs à un concurrent.
Ex: Mediawan LUX a l'exclusivité SVOD France pour SCAB VENDOR sur EXPLORE,
    mais SCAB VENDOR apparaît sur Netflix France → violation par le vendeur.
"""

import asyncio
import logging
from datetime import datetime

from plateformes_france import get_competing_svod_platforms, is_available_in_territory
import db
from intrusion_scanner import scan_justwatch, scan_youtube, Violation, Detection, fuzzy_match

logger = logging.getLogger(__name__)


async def check_exclusivity_breach(
    deal_id: str,
    programme: str,
    media: str,
    territoires: list[str],
    chaines_autorisees: list[str],
    youtube_api_key: str = None
) -> list[Violation]:
    """
    Vérifie qu'aucun concurrent n'a reçu les mêmes droits exclusifs.
    Retourne les violations trouvées (présence sur plateforme concurrente).
    """
    violations = []

    for territoire in territoires:
        # Plateformes concurrentes dans ce territoire
        concurrents = get_competing_svod_platforms(
            exclude=chaines_autorisees,
            territoire=territoire
        )

        # Scan JustWatch pour chaque concurrent potentiel
        tasks = [scan_justwatch(programme, territoire, chaine_autorisee) for chaine_autorisee in chaines_autorisees]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_detections: list[Detection] = []
        for r in results:
            if not isinstance(r, Exception):
                all_detections.extend(r)

        for det in all_detections:
            if det.plateforme in concurrents and is_available_in_territory(det.plateforme, territoire):
                violations.append(Violation(
                    detection=det,
                    deal_id=deal_id,
                    severite="CRITIQUE",
                    type_violation=f"Violation exclusivité {media} par le vendeur",
                    description=(
                        f"[VUE ACHETEUR] {programme} présent sur {det.plateforme} ({territoire}) "
                        f"alors que vous avez l'exclusivité {media} via {', '.join(chaines_autorisees)}. "
                        f"Le vendeur a potentiellement accordé les mêmes droits à un concurrent."
                    )
                ))

    # YouTube — uploads officiels d'une autre chaîne
    if youtube_api_key:
        yt_detections = await scan_youtube(programme, youtube_api_key)
        for det in yt_detections:
            violations.append(Violation(
                detection=det,
                deal_id=deal_id,
                severite="HAUTE",
                type_violation="Contenu disponible sur YouTube hors licence",
                description=(
                    f"[VUE ACHETEUR] {programme} trouvé sur YouTube ({det.metadata.get('channel')}) "
                    f"— vérifier s'il s'agit d'un upload officiel d'un autre ayant-droit."
                )
            ))

    return violations


async def run_acheteur_scan(youtube_api_key: str = None) -> list[Violation]:
    """
    Scan complet vue acheteur :
    Parcourt tous les blocs exclusifs dont on est licencié
    et vérifie l'absence de violations par le vendeur.
    """
    blocs = db.get_blocs_actifs()
    blocs_exclusifs = [b for b in blocs if b["type"] == "exclusif"]

    logger.info(f"Vue acheteur : {len(blocs_exclusifs)} blocs exclusifs à surveiller")

    all_violations = []
    for bloc in blocs_exclusifs:
        violations = await check_exclusivity_breach(
            deal_id=bloc["deal_id"],
            programme=bloc["programme"],
            media=bloc["media"],
            territoires=bloc["territoires"],
            chaines_autorisees=bloc["chaines"],
            youtube_api_key=youtube_api_key
        )

        for v in violations:
            diff_id = db.save_diffusion({
                "scraper_id": None,
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

    logger.info(f"Vue acheteur terminée : {len(all_violations)} violations")
    return all_violations


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db.init_db()
    violations = asyncio.run(run_acheteur_scan())
    for v in violations:
        print(f"[{v.severite}] {v.description}")
