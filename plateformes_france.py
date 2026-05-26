"""
Référentiel des plateformes de streaming opérant en France et territoires contractuels.
geo_disponible = territoires où la plateforme est réellement accessible.
"""

PLATEFORMES_SVOD = {
    # --- Plateformes majeures ---
    "Netflix":          {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH", "Monaco", "Andorre", "Dom-Tom"], "justwatch_id": "nfx"},
    "Disney+":          {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH", "Monaco", "Dom-Tom"], "justwatch_id": "dnp"},
    "Prime Video":      {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH", "Monaco", "Andorre", "Dom-Tom"], "justwatch_id": "amp"},
    "Apple TV+":        {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH", "Monaco", "Dom-Tom"], "justwatch_id": "atp"},
    "Max":              {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH"], "justwatch_id": "hbm"},
    "Paramount+":       {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH"], "justwatch_id": "pmp"},

    # --- Plateformes françaises / francophones ---
    "Canal+":           {"type": "SVOD", "geo_disponible": ["France", "Dom-Tom", "Monaco", "Andorre"], "justwatch_id": "cnl"},
    "OCS":              {"type": "SVOD", "geo_disponible": ["France", "Dom-Tom"], "justwatch_id": "ocs"},
    "EXPLORE":          {"type": "SVOD", "geo_disponible": ["France", "Dom-Tom"], "justwatch_id": None},
    "Insomnia":         {"type": "SVOD", "geo_disponible": ["France", "Dom-Tom", "Benelux", "CH", "Monaco"], "justwatch_id": None},
    "Shadowz":          {"type": "SVOD", "geo_disponible": ["France", "Benelux"], "justwatch_id": "shz"},
    "Tënk":             {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH"], "justwatch_id": "tnk"},
    "Docsville":        {"type": "SVOD", "geo_disponible": ["France"], "justwatch_id": None},
    "Society+":         {"type": "SVOD", "geo_disponible": ["France"], "justwatch_id": None},
    "Alchimie":         {"type": "SVOD", "geo_disponible": ["France", "Dom-Tom"], "justwatch_id": None},
    "Culturebox":       {"type": "SVOD", "geo_disponible": ["France"], "justwatch_id": None},
    "Mubi":             {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH"], "justwatch_id": "mub"},
    "Crunchyroll":      {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH", "Monaco"], "justwatch_id": "cru"},
    "ADN":              {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH"], "justwatch_id": "adn"},
    "Viki":             {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH"], "justwatch_id": "rak"},
    "Curiosity Stream": {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH"], "justwatch_id": "cst"},
    "Spicee":           {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH", "Monaco"], "justwatch_id": None},
    "Arte":             {"type": "SVOD", "geo_disponible": ["France", "Benelux", "CH", "Andorre"], "justwatch_id": "art"},
    "France.tv":        {"type": "SVOD", "geo_disponible": ["France", "Dom-Tom"], "justwatch_id": "frt"},
    "Salto":            {"type": "SVOD", "geo_disponible": [], "justwatch_id": None, "defunct": True},

    # --- Chaînes avec Amazon Channel ---
    "Insomnia Amazon Channel": {"type": "SVOD", "geo_disponible": ["France", "Dom-Tom", "Benelux"], "justwatch_id": None, "parent": "Prime Video"},
    "OCS Amazon Channel":      {"type": "SVOD", "geo_disponible": ["France", "Dom-Tom"], "justwatch_id": None, "parent": "Prime Video"},
    "Shadowz Amazon Channel":  {"type": "SVOD", "geo_disponible": ["France", "Benelux"], "justwatch_id": None, "parent": "Prime Video"},

    # --- Hors France (pas de violation possible sur territoires FR) ---
    "Tubi":             {"type": "AVOD", "geo_disponible": ["USA", "Canada", "Mexique", "Australie"], "justwatch_id": "tub", "hors_france": True},
    "Peacock":          {"type": "SVOD", "geo_disponible": ["USA"], "justwatch_id": "pck", "hors_france": True},
    "Hulu":             {"type": "SVOD", "geo_disponible": ["USA", "Japon"], "justwatch_id": "hlu", "hors_france": True},
}

PLATEFORMES_AVOD = {
    "YouTube":          {"type": "AVOD", "geo_disponible": ["France", "Benelux", "CH", "Monaco", "Andorre", "Dom-Tom", "USA"]},
    "Dailymotion":      {"type": "AVOD", "geo_disponible": ["France", "Benelux", "CH", "Monaco", "Andorre"]},
    "Pluto TV":         {"type": "AVOD", "geo_disponible": ["France", "Benelux", "CH"]},
    "Molotov":          {"type": "AVOD", "geo_disponible": ["France", "Dom-Tom", "Benelux", "CH"]},
    "Samsung TV+":      {"type": "AVOD", "geo_disponible": ["France", "Benelux", "CH"]},
    "LG Channels":      {"type": "AVOD", "geo_disponible": ["France", "Benelux", "CH"]},
    "Rakuten TV":       {"type": "AVOD", "geo_disponible": ["France", "Benelux", "CH", "Monaco"]},
    "Plex":             {"type": "AVOD", "geo_disponible": ["France", "Benelux", "CH", "USA"]},
    "France.tv Slash":  {"type": "AVOD", "geo_disponible": ["France"]},
    "6play":            {"type": "AVOD", "geo_disponible": ["France", "Benelux"]},
    "MyTF1":            {"type": "AVOD", "geo_disponible": ["France"]},
}

CHAINES_PAYTV = {
    "RTL9":     {"type": "Pay-TV", "geo_disponible": ["France", "Benelux", "CH", "Monaco", "Andorre"]},
    "Canal+":   {"type": "Pay-TV", "geo_disponible": ["France", "Dom-Tom", "Monaco", "Andorre"]},
    "OCS":      {"type": "Pay-TV", "geo_disponible": ["France", "Dom-Tom"]},
    "beIN":     {"type": "Pay-TV", "geo_disponible": ["France", "Monaco"]},
    "Ciné+":    {"type": "Pay-TV", "geo_disponible": ["France", "Dom-Tom"]},
    "Sky":      {"type": "Pay-TV", "geo_disponible": ["Benelux", "CH", "UK"]},
    "Proximus": {"type": "Pay-TV", "geo_disponible": ["Benelux"]},
}


def is_available_in_territory(plateforme: str, territoire: str) -> bool:
    """Retourne True si la plateforme opère réellement dans ce territoire."""
    all_platforms = {**PLATEFORMES_SVOD, **PLATEFORMES_AVOD, **CHAINES_PAYTV}
    p = all_platforms.get(plateforme)
    if not p:
        return False
    if p.get("defunct"):
        return False
    return territoire in p.get("geo_disponible", [])


def get_competing_svod_platforms(exclude: list[str], territoire: str) -> list[str]:
    """Retourne les plateformes SVOD concurrentes disponibles dans un territoire."""
    return [
        name for name, info in PLATEFORMES_SVOD.items()
        if name not in exclude
        and not info.get("defunct")
        and not info.get("hors_france")
        and territoire in info.get("geo_disponible", [])
    ]
