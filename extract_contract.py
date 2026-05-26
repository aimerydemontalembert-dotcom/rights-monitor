"""
extract_contract.py — Extraction de contrats PDF via pdfplumber + Claude API.
Retourne un JSON structuré conforme au schéma Rights Monitor.
"""

import json
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import anthropic
except ImportError:
    anthropic = None


CLAUDE_MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """Tu es un expert en droits audiovisuels. Tu analyses des Deal Memos (contrats de licence)
au format PDF et tu en extrais un JSON structuré précis.

Règles d'extraction :
- Identifie tous les blocs de droits (exclusifs, non-exclusifs, blocages/holdbacks)
- Pour chaque bloc, extrais : programme, type, media, territoires, chaines, dates, quotas, restrictions
- Les médias possibles : SVOD, AVOD, FVOD, Pay-TV, Free-TV, Catch-up
- Les types possibles : exclusif, non-exclusif, blocage
- Normalise les dates au format YYYY-MM-DD
- Si une information est absente, mets null
- Retourne UNIQUEMENT le JSON, sans texte autour

Format de sortie :
{
  "deal_id": "string",
  "concedant": "string",
  "licencie": "string",
  "blocs_droits": [
    {
      "programme": "string",
      "type": "exclusif|non-exclusif|blocage",
      "media": "SVOD|AVOD|FVOD|Pay-TV|Free-TV|Catch-up",
      "territoires": ["string"],
      "chaines": ["string"],
      "date_debut": "YYYY-MM-DD",
      "date_fin": "YYYY-MM-DD",
      "diffusions_max": null,
      "restrictions": ["string"]
    }
  ],
  "blocages": [
    {
      "media": ["string"],
      "territoires": ["string"],
      "date_debut": "YYYY-MM-DD",
      "date_fin": "YYYY-MM-DD"
    }
  ]
}"""


def extract_text_from_pdf(pdf_path: str) -> str:
    if pdfplumber is None:
        raise ImportError("pdfplumber non installé : pip install pdfplumber")
    with pdfplumber.open(pdf_path) as pdf:
        pages = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def extract_contract_data(pdf_path: str, api_key: str = None) -> dict:
    """
    Lit le PDF et appelle Claude pour extraire le JSON structuré.
    api_key : optionnel si ANTHROPIC_API_KEY est défini en variable d'environnement.
    """
    if anthropic is None:
        raise ImportError("anthropic non installé : pip install anthropic")

    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        raise ValueError(f"Impossible d'extraire le texte du PDF : {pdf_path}")

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Voici le texte du contrat Deal Memo à analyser :\n\n{text[:15000]}"
            }
        ]
    )

    raw = message.content[0].text.strip()

    # Nettoyage si Claude a quand même mis des backticks
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


def extract_and_save(pdf_path: str, output_path: str = None, api_key: str = None) -> dict:
    """Extrait le contrat et sauvegarde le JSON dans un fichier."""
    data = extract_contract_data(pdf_path, api_key)

    if output_path is None:
        output_path = Path(pdf_path).with_suffix(".json")

    Path(output_path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"JSON extrait : {output_path}")
    return data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_contract.py <fichier.pdf> [sortie.json]")
        sys.exit(1)

    pdf = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    result = extract_and_save(pdf, out)
    print(json.dumps(result, indent=2, ensure_ascii=False))
