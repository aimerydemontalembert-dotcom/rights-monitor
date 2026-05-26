"""
main.py — API FastAPI pour Rights Monitor.
Endpoints : contrats, violations, scrapers, dashboard stats.
"""

import asyncio
import os
from datetime import datetime
from typing import Literal

try:
    from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse
    from pydantic import BaseModel
except ImportError:
    raise ImportError("fastapi non installé : pip install fastapi uvicorn python-multipart")

import db
from extract_contract import extract_contract_data
from intrusion_scanner import run_all_scrapers
from scanner_acheteur import run_acheteur_scan

app = FastAPI(
    title="Rights Monitor API",
    description="Surveillance des droits audiovisuels — Mediawan LUX",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")


# ── Modèles Pydantic ──────────────────────────────────────────────────────────

class AlerteStatutUpdate(BaseModel):
    statut: Literal["ouverte", "en_cours", "resolue", "ignoree"]


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/stats")
def get_stats():
    return db.get_stats()


# ── Contrats ──────────────────────────────────────────────────────────────────

@app.get("/contrats")
def list_contrats():
    return db.list_contrats()


@app.get("/contrats/{deal_id}")
def get_contrat(deal_id: str):
    c = db.get_contrat(deal_id)
    if not c:
        raise HTTPException(404, f"Contrat {deal_id} non trouvé")
    return c


@app.post("/contrats/import")
async def import_contrat_pdf(file: UploadFile = File(...)):
    """
    Upload un PDF de Deal Memo → extraction IA → import en base.
    Crée automatiquement les scrapers correspondants.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Le fichier doit être un PDF")

    # Sauvegarde temporaire
    tmp_path = f"/tmp/{file.filename}"
    content = await file.read()
    with open(tmp_path, "wb") as f:
        f.write(content)

    try:
        data = extract_contract_data(tmp_path, api_key=ANTHROPIC_API_KEY)
        contrat_id = db.import_contrat(data, fichier_pdf=file.filename)
        scrapers = db.list_scrapers(actif_only=True)
        nb_scrapers = sum(1 for s in scrapers if s["deal_id"] == data["deal_id"])

        return {
            "success": True,
            "deal_id": data["deal_id"],
            "contrat_id": contrat_id,
            "programme_count": len({b["programme"] for b in data.get("blocs_droits", [])}),
            "scrapers_crees": nb_scrapers,
            "data": data,
        }
    except Exception as e:
        raise HTTPException(500, f"Erreur extraction : {str(e)}")
    finally:
        import os as _os
        if _os.path.exists(tmp_path):
            _os.remove(tmp_path)


@app.post("/contrats/import/json")
def import_contrat_json(data: dict):
    """Import direct d'un JSON déjà extrait (pour tests)."""
    try:
        contrat_id = db.import_contrat(data)
        return {"success": True, "contrat_id": contrat_id, "deal_id": data["deal_id"]}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Scrapers ──────────────────────────────────────────────────────────────────

@app.get("/scrapers")
def list_scrapers(actif_only: bool = True):
    return db.list_scrapers(actif_only=actif_only)


@app.post("/scrapers/run")
async def run_scrapers(background_tasks: BackgroundTasks, vue: Literal["vendeur", "acheteur", "all"] = "all"):
    """Lance un scan immédiat en arrière-plan."""
    async def do_scan():
        if vue in ("vendeur", "all"):
            await run_all_scrapers(youtube_api_key=YOUTUBE_API_KEY)
        if vue in ("acheteur", "all"):
            await run_acheteur_scan(youtube_api_key=YOUTUBE_API_KEY)

    background_tasks.add_task(do_scan)
    return {"message": f"Scan {vue} lancé en arrière-plan"}


# ── Violations / Alertes ──────────────────────────────────────────────────────

@app.get("/violations")
def list_violations(
    statut: str = None,
    severite: str = None,
    programme: str = None,
    deal_id: str = None
):
    alertes = db.list_alertes(statut=statut, severite=severite)

    if programme:
        alertes = [a for a in alertes if programme.lower() in a["programme"].lower()]
    if deal_id:
        alertes = [a for a in alertes if a["deal_id"] == deal_id]

    return {
        "total": len(alertes),
        "critiques": sum(1 for a in alertes if a["severite"] == "CRITIQUE"),
        "hautes": sum(1 for a in alertes if a["severite"] == "HAUTE"),
        "moyennes": sum(1 for a in alertes if a["severite"] == "MOYENNE"),
        "alertes": alertes,
    }


@app.patch("/violations/{alerte_id}")
def update_violation(alerte_id: int, body: AlerteStatutUpdate):
    db.update_alerte_statut(alerte_id, body.statut)
    return {"success": True, "alerte_id": alerte_id, "statut": body.statut}


@app.get("/violations/export/csv")
def export_violations_csv(statut: str = None, severite: str = None):
    """Export CSV des violations pour suivi."""
    import csv
    import io

    alertes = db.list_alertes(statut=statut, severite=severite)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "deal_id", "programme", "severite", "type_violation",
        "description", "plateforme", "territoire", "url", "statut", "created_at"
    ])
    writer.writeheader()
    for a in alertes:
        writer.writerow({k: a.get(k, "") for k in writer.fieldnames})

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=violations_rights_monitor.csv"}
    )


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    db.init_db()
    print("Rights Monitor API démarrée — base initialisée")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
