"""
run_demo2.py — Démo 90 jours de scraping RTL9 simulé pour FEMMES DE LOI.
Génère un historique réaliste de diffusions avec quelques violations.
"""

import asyncio
import json
import random
from datetime import date, timedelta
import db

PROGRAMME = "FEMMES DE LOI"
DEAL_ID = "42222"
SAISONS = list(range(1, 6))  # S1 à S5, 6 épisodes chacune
EPISODES_PAR_SAISON = 6

CASES_VALIDES = [("09:00", "09:50"), ("10:00", "10:50"), ("11:00", "11:50"), ("12:00", "12:50"), ("13:00", "13:50")]
CASES_HORS_CONTRAT = [("06:00", "06:50"), ("15:30", "16:20"), ("20:50", "21:40")]

def generate_diffusions(days: int = 90) -> list[dict]:
    """Génère un programme de diffusions RTL9 sur 90 jours avec violations réalistes."""
    diffusions = []
    start = date.today() - timedelta(days=days)
    ep_compteurs: dict[tuple, int] = {}

    for day_offset in range(days):
        current_date = start + timedelta(days=day_offset)
        # RTL9 diffuse 2-3 épisodes par jour en semaine
        if current_date.weekday() >= 5:  # Week-end → moins de diffusions
            nb = random.randint(0, 1)
        else:
            nb = random.randint(2, 3)

        for _ in range(nb):
            saison = random.choice(SAISONS)
            episode = random.randint(1, EPISODES_PAR_SAISON)
            key = (saison, episode)
            ep_compteurs[key] = ep_compteurs.get(key, 0) + 1

            # 5% chance d'être hors case horaire (violation)
            if random.random() < 0.05:
                heure_debut, _ = random.choice(CASES_HORS_CONTRAT)
                violation = True
            else:
                heure_debut, _ = random.choice(CASES_VALIDES)
                violation = False

            diffusions.append({
                "date": current_date.isoformat(),
                "heure": heure_debut,
                "saison": saison,
                "episode": episode,
                "compteur": ep_compteurs[key],
                "hors_case": violation,
                "quota_depasse": ep_compteurs[key] > 2,
            })

    return diffusions


def print_rapport(diffusions: list[dict]):
    violations_quota = [d for d in diffusions if d["quota_depasse"]]
    violations_case = [d for d in diffusions if d["hors_case"]]

    print(f"\n{'='*60}")
    print(f"RAPPORT DEMO — {PROGRAMME} (Deal {DEAL_ID})")
    print(f"{'='*60}")
    print(f"Période       : 90 derniers jours")
    print(f"Total diffusions : {len(diffusions)}")
    print(f"{'─'*60}")
    print(f"[CRITIQUE] Quotas dépassés    : {len(violations_quota)} diffusions")
    print(f"[HAUTE]    Hors case horaire  : {len(violations_case)} diffusions")
    print(f"{'─'*60}")

    if violations_quota:
        print("\nDépassements de quota (extrait) :")
        seen = set()
        for d in violations_quota[:5]:
            key = (d["saison"], d["episode"])
            if key not in seen:
                seen.add(key)
                print(f"  S{d['saison']:02d}E{d['episode']:02d} — {d['compteur']} diffusions (max: 2)")

    if violations_case:
        print("\nDiffusions hors case horaire (extrait) :")
        for d in violations_case[:5]:
            print(f"  S{d['saison']:02d}E{d['episode']:02d} — {d['date']} à {d['heure']} (case: 09h–14h)")

    print(f"\n{'='*60}")


async def run_demo():
    db.init_db()
    print(f"Génération démo 90 jours — {PROGRAMME}")
    diffusions = generate_diffusions(90)

    # Enregistrement en base
    for diff in diffusions:
        if diff["quota_depasse"] or diff["hors_case"]:
            diff_id = db.save_diffusion({
                "scraper_id": None,
                "deal_id": DEAL_ID,
                "programme": PROGRAMME,
                "plateforme": "RTL9",
                "territoire": "France",
                "source": "rtl9_quota",
                "date_diffusion": diff["date"],
                "heure_diffusion": diff["heure"],
                "saison": diff["saison"],
                "episode": diff["episode"],
            })
            if diff["quota_depasse"]:
                db.save_alerte({
                    "diffusion_id": diff_id,
                    "deal_id": DEAL_ID,
                    "programme": PROGRAMME,
                    "severite": "CRITIQUE",
                    "type_violation": "quota_depasse",
                    "description": (
                        f"S{diff['saison']:02d}E{diff['episode']:02d} diffusé "
                        f"{diff['compteur']} fois (max contractuel : 2)"
                    ),
                    "plateforme": "RTL9",
                    "territoire": "France",
                })
            elif diff["hors_case"]:
                db.save_alerte({
                    "diffusion_id": diff_id,
                    "deal_id": DEAL_ID,
                    "programme": PROGRAMME,
                    "severite": "HAUTE",
                    "type_violation": "hors_case_horaire",
                    "description": (
                        f"S{diff['saison']:02d}E{diff['episode']:02d} diffusé à {diff['heure']} "
                        f"(case autorisée : 09:00–14:00)"
                    ),
                    "plateforme": "RTL9",
                    "territoire": "France",
                })

    print_rapport(diffusions)
    stats = db.get_stats()
    print(f"\nBase de données : {stats}")


if __name__ == "__main__":
    asyncio.run(run_demo())
