"""
db.py — ORM maison SQLite pour Rights Monitor.
Gère l'import de contrats JSON et l'activation automatique des scrapers.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "rights_monitor.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


# ── Contrats ──────────────────────────────────────────────────────────────────

def import_contrat(data: dict, fichier_pdf: str = None) -> int:
    """
    Insère un contrat extrait par l'IA.
    Crée automatiquement les blocs_droits et les scrapers_actifs correspondants.
    Retourne l'id du contrat créé.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT OR REPLACE INTO contrats (deal_id, concedant, licencie, fichier_pdf, json_brut)
               VALUES (?, ?, ?, ?, ?)""",
            (data["deal_id"], data["concedant"], data["licencie"],
             fichier_pdf, json.dumps(data, ensure_ascii=False))
        )
        contrat_id = cur.lastrowid

        for bloc in data.get("blocs_droits", []):
            conn.execute(
                """INSERT INTO blocs_droits
                   (contrat_id, deal_id, programme, type, media, territoires, chaines,
                    date_debut, date_fin, diffusions_max, restrictions)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    contrat_id,
                    data["deal_id"],
                    bloc["programme"],
                    bloc["type"],
                    bloc["media"],
                    json.dumps(bloc.get("territoires", []), ensure_ascii=False),
                    json.dumps(bloc.get("chaines", []), ensure_ascii=False),
                    bloc["date_debut"],
                    bloc["date_fin"],
                    bloc.get("diffusions_max"),
                    json.dumps(bloc.get("restrictions", []), ensure_ascii=False),
                )
            )
            _create_scrapers(conn, contrat_id, data["deal_id"], bloc)

        return contrat_id


def _create_scrapers(conn, contrat_id: int, deal_id: str, bloc: dict):
    """Crée 1 scraper par combinaison programme × chaine × territoire."""
    if bloc["type"] == "blocage":
        return

    chaines = bloc.get("chaines") or ["*"]
    territoires = bloc.get("territoires") or ["France"]

    for chaine in chaines:
        for territoire in territoires:
            conn.execute(
                """INSERT OR IGNORE INTO scrapers_actifs
                   (contrat_id, deal_id, programme, chaine, territoire, media, type_vue)
                   VALUES (?, ?, ?, ?, ?, ?, 'vendeur')""",
                (contrat_id, deal_id, bloc["programme"], chaine, territoire, bloc["media"])
            )


def get_contrat(deal_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM contrats WHERE deal_id = ?", (deal_id,)).fetchone()
        return dict(row) if row else None


def list_contrats() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM contrats ORDER BY date_import DESC").fetchall()
        return [dict(r) for r in rows]


# ── Blocs droits ──────────────────────────────────────────────────────────────

def get_blocs_actifs(programme: str = None) -> list[dict]:
    """Retourne les blocs dont la fenêtre est encore en cours."""
    today = datetime.now().date().isoformat()
    query = "SELECT * FROM blocs_droits WHERE date_debut <= ? AND date_fin >= ?"
    params = [today, today]
    if programme:
        query += " AND programme LIKE ?"
        params.append(f"%{programme}%")
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["territoires"] = json.loads(d["territoires"])
            d["chaines"] = json.loads(d["chaines"] or "[]")
            d["restrictions"] = json.loads(d["restrictions"] or "[]")
            result.append(d)
        return result


# ── Scrapers ──────────────────────────────────────────────────────────────────

def list_scrapers(actif_only: bool = True) -> list[dict]:
    with get_conn() as conn:
        query = "SELECT * FROM scrapers_actifs"
        if actif_only:
            query += " WHERE actif = 1"
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]


def update_scraper_timestamp(scraper_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE scrapers_actifs SET dernier_scan = ? WHERE id = ?",
            (datetime.now().isoformat(), scraper_id)
        )


# ── Diffusions & Alertes ──────────────────────────────────────────────────────

def save_diffusion(data: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO diffusions_detectees
               (scraper_id, deal_id, programme, plateforme, territoire, url,
                date_diffusion, heure_diffusion, saison, episode, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("scraper_id"), data["deal_id"], data["programme"],
                data["plateforme"], data["territoire"], data.get("url"),
                data.get("date_diffusion"), data.get("heure_diffusion"),
                data.get("saison"), data.get("episode"), data["source"]
            )
        )
        return cur.lastrowid


def save_alerte(data: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO alertes
               (diffusion_id, deal_id, programme, severite, type_violation,
                description, plateforme, territoire, url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("diffusion_id"), data["deal_id"], data["programme"],
                data["severite"], data["type_violation"], data["description"],
                data.get("plateforme"), data.get("territoire"), data.get("url")
            )
        )
        return cur.lastrowid


def list_alertes(statut: str = None, severite: str = None) -> list[dict]:
    query = "SELECT * FROM alertes"
    clauses, params = [], []
    if statut:
        clauses.append("statut = ?")
        params.append(statut)
    if severite:
        clauses.append("severite = ?")
        params.append(severite)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def update_alerte_statut(alerte_id: int, statut: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE alertes SET statut = ?, updated_at = ? WHERE id = ?",
            (statut, datetime.now().isoformat(), alerte_id)
        )


# ── Stats dashboard ───────────────────────────────────────────────────────────

def get_stats() -> dict:
    with get_conn() as conn:
        return {
            "contrats_actifs": conn.execute(
                "SELECT COUNT(*) FROM contrats"
            ).fetchone()[0],
            "scrapers_actifs": conn.execute(
                "SELECT COUNT(*) FROM scrapers_actifs WHERE actif = 1"
            ).fetchone()[0],
            "alertes_ouvertes": conn.execute(
                "SELECT COUNT(*) FROM alertes WHERE statut = 'ouverte'"
            ).fetchone()[0],
            "violations_critiques": conn.execute(
                "SELECT COUNT(*) FROM alertes WHERE severite = 'CRITIQUE' AND statut = 'ouverte'"
            ).fetchone()[0],
        }


if __name__ == "__main__":
    init_db()
    print("Base initialisée :", DB_PATH)
    print("Stats :", get_stats())
