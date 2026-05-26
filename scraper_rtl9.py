"""
scraper_rtl9.py — Surveillance des quotas de diffusion RTL9.
Compte les diffusions par épisode vs le maximum contractuel.
Contrat type : Deal 42222 FEMMES DE LOI — max 2 diff/épisode + 4 rediff, case 9h-14h.
"""

import re
import logging
import asyncio
from datetime import datetime, date, timedelta
from collections import defaultdict

try:
    import httpx
except ImportError:
    httpx = None

try:
    from xml.etree import ElementTree as ET
except ImportError:
    ET = None

import db

logger = logging.getLogger(__name__)

RTL9_EPG_URL = "https://raw.githubusercontent.com/iptv-org/epg/master/sites/rtl9.be/rtl9.be.epg.xml"

# Contraintes Deal 42222 FEMMES DE LOI
RTL9_CONTRAINTES = {
    "FEMMES DE LOI": {
        "diffusions_max_par_episode": 2,
        "rediffusions_max": 4,
        "case_horaire_debut": "09:00",
        "case_horaire_fin": "14:00",
        "catch_up_jours": 30,
    }
}


@dataclass_like := type("QuotaEpisode", (), {
    "__init__": lambda self, s, e: (
        setattr(self, "saison", s),
        setattr(self, "episode", e),
        setattr(self, "diffusions", []),
    ) and None
})

class QuotaEpisode:
    def __init__(self, saison: int, episode: int):
        self.saison = saison
        self.episode = episode
        self.diffusions: list[dict] = []

    @property
    def nb_diffusions(self) -> int:
        return len(self.diffusions)

    def hors_case_horaire(self, case_debut: str, case_fin: str) -> list[dict]:
        violations = []
        for diff in self.diffusions:
            h = diff.get("heure", "")
            if h and not (case_debut <= h <= case_fin):
                violations.append(diff)
        return violations


async def fetch_epg_rtl9(days_back: int = 7) -> str:
    """Récupère le fichier EPG RTL9 depuis iptv-org."""
    if httpx is None:
        raise ImportError("httpx non installé")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(RTL9_EPG_URL)
        resp.raise_for_status()
        return resp.text


def parse_epg_xml(xml_text: str, programme_cible: str) -> list[dict]:
    """Parse le XML XMLTV et retourne les diffusions correspondant au programme."""
    if ET is None:
        return []

    diffusions = []
    try:
        root = ET.fromstring(xml_text)
        for prog in root.findall(".//programme"):
            title_el = prog.find("title")
            if title_el is None:
                continue
            titre = title_el.text or ""
            if programme_cible.lower() not in titre.lower():
                continue

            start = prog.get("start", "")
            # Format XMLTV : 20241201143000 +0100
            dt_str = start[:14]
            try:
                dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
            except ValueError:
                continue

            # Extraire S/E depuis le titre ou la description
            saison, episode = _extract_se(titre, prog)

            diffusions.append({
                "titre": titre,
                "date": dt.date().isoformat(),
                "heure": dt.strftime("%H:%M"),
                "saison": saison,
                "episode": episode,
                "raw_start": start,
            })

    except ET.ParseError as e:
        logger.error(f"Parse EPG error: {e}")

    return diffusions


def _extract_se(titre: str, prog_el) -> tuple[int | None, int | None]:
    """Tente d'extraire saison/épisode depuis le titre ou les métadonnées XMLTV."""
    patterns = [
        r"S(\d+)E(\d+)",
        r"[Ss]aison\s*(\d+).*[Eeépisode]+\s*(\d+)",
        r"(\d+)x(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, titre)
        if m:
            return int(m.group(1)), int(m.group(2))

    # Chercher dans episode-num
    ep_num = prog_el.find("episode-num")
    if ep_num is not None and ep_num.get("system") == "xmltv_ns":
        # Format: S.E.P (0-indexed)
        parts = (ep_num.text or "").split(".")
        if len(parts) >= 2:
            try:
                return int(parts[0].strip()) + 1, int(parts[1].strip()) + 1
            except ValueError:
                pass

    return None, None


def check_quotas(diffusions: list[dict], contraintes: dict) -> list[dict]:
    """Vérifie les dépassements de quota et les violations de case horaire."""
    violations = []
    max_diff = contraintes.get("diffusions_max_par_episode", 2)
    case_debut = contraintes.get("case_horaire_debut", "00:00")
    case_fin = contraintes.get("case_horaire_fin", "23:59")

    # Regrouper par épisode
    episodes: dict[tuple, list] = defaultdict(list)
    for diff in diffusions:
        key = (diff.get("saison"), diff.get("episode"))
        episodes[key].append(diff)

    for (saison, episode), diffs in episodes.items():
        ep_label = f"S{saison:02d}E{episode:02d}" if saison and episode else "inconnu"

        # Quota dépassé
        if len(diffs) > max_diff:
            violations.append({
                "type": "quota_depasse",
                "severite": "CRITIQUE",
                "episode": ep_label,
                "nb_diffusions": len(diffs),
                "max_autorise": max_diff,
                "description": (
                    f"{ep_label} diffusé {len(diffs)} fois sur RTL9 "
                    f"(max contractuel : {max_diff})"
                ),
                "diffusions": diffs,
            })

        # Hors case horaire
        for diff in diffs:
            heure = diff.get("heure", "")
            if heure and not (case_debut <= heure <= case_fin):
                violations.append({
                    "type": "hors_case_horaire",
                    "severite": "HAUTE",
                    "episode": ep_label,
                    "heure_diffusion": heure,
                    "case_autorisee": f"{case_debut}–{case_fin}",
                    "description": (
                        f"{ep_label} diffusé à {heure} sur RTL9 "
                        f"(case autorisée : {case_debut}–{case_fin})"
                    ),
                    "diffusions": [diff],
                })

    return violations


async def run_rtl9_scan(programme: str = "FEMMES DE LOI", deal_id: str = "42222") -> list[dict]:
    """Scan complet RTL9 pour un programme donné."""
    logger.info(f"Scan RTL9 : {programme} (deal {deal_id})")

    try:
        xml_text = await fetch_epg_rtl9()
    except Exception as e:
        logger.error(f"Impossible de récupérer l'EPG RTL9 : {e}")
        return []

    diffusions = parse_epg_xml(xml_text, programme)
    logger.info(f"{len(diffusions)} diffusions trouvées pour {programme}")

    contraintes = RTL9_CONTRAINTES.get(programme, {
        "diffusions_max_par_episode": 2,
        "case_horaire_debut": "09:00",
        "case_horaire_fin": "14:00",
    })

    violations = check_quotas(diffusions, contraintes)

    for v in violations:
        for diff in v.get("diffusions", []):
            diff_id = db.save_diffusion({
                "scraper_id": None,
                "deal_id": deal_id,
                "programme": programme,
                "plateforme": "RTL9",
                "territoire": "France",
                "source": "rtl9_quota",
                "date_diffusion": diff.get("date"),
                "heure_diffusion": diff.get("heure"),
            })
            db.save_alerte({
                "diffusion_id": diff_id,
                "deal_id": deal_id,
                "programme": programme,
                "severite": v["severite"],
                "type_violation": v["type"],
                "description": v["description"],
                "plateforme": "RTL9",
                "territoire": "France",
            })

    logger.info(f"RTL9 scan terminé : {len(violations)} violations")
    return violations


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db.init_db()
    violations = asyncio.run(run_rtl9_scan())
    for v in violations:
        print(f"[{v['severite']}] {v['description']}")
