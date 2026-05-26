-- Rights Monitor — SQLite Schema

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS contrats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id     TEXT NOT NULL UNIQUE,
    concedant   TEXT NOT NULL,
    licencie    TEXT NOT NULL,
    fichier_pdf TEXT,
    date_import DATETIME DEFAULT CURRENT_TIMESTAMP,
    json_brut   TEXT
);

CREATE TABLE IF NOT EXISTS blocs_droits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contrat_id      INTEGER NOT NULL REFERENCES contrats(id) ON DELETE CASCADE,
    deal_id         TEXT NOT NULL,
    programme       TEXT NOT NULL,
    type            TEXT NOT NULL CHECK(type IN ('exclusif','non-exclusif','blocage')),
    media           TEXT NOT NULL,   -- SVOD, AVOD, FVOD, Pay-TV, Free-TV, Catch-up
    territoires     TEXT NOT NULL,   -- JSON array
    chaines         TEXT,            -- JSON array, null pour blocages
    date_debut      DATE NOT NULL,
    date_fin        DATE NOT NULL,
    diffusions_max  INTEGER,         -- null = illimité
    restrictions    TEXT             -- JSON array de strings
);

CREATE TABLE IF NOT EXISTS scrapers_actifs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contrat_id  INTEGER NOT NULL REFERENCES contrats(id) ON DELETE CASCADE,
    deal_id     TEXT NOT NULL,
    programme   TEXT NOT NULL,
    chaine      TEXT NOT NULL,
    territoire  TEXT NOT NULL,
    media       TEXT NOT NULL,
    type_vue    TEXT NOT NULL CHECK(type_vue IN ('vendeur','acheteur')),
    actif       INTEGER NOT NULL DEFAULT 1,
    dernier_scan DATETIME,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS diffusions_detectees (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scraper_id      INTEGER NOT NULL REFERENCES scrapers_actifs(id) ON DELETE CASCADE,
    deal_id         TEXT NOT NULL,
    programme       TEXT NOT NULL,
    plateforme      TEXT NOT NULL,
    territoire      TEXT NOT NULL,
    url             TEXT,
    date_detection  DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_diffusion  DATE,
    heure_diffusion TEXT,
    saison          INTEGER,
    episode         INTEGER,
    source          TEXT NOT NULL  -- justwatch, youtube, epg_free, epg_pay, rtl9_quota
);

CREATE TABLE IF NOT EXISTS alertes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    diffusion_id    INTEGER REFERENCES diffusions_detectees(id),
    deal_id         TEXT NOT NULL,
    programme       TEXT NOT NULL,
    severite        TEXT NOT NULL CHECK(severite IN ('CRITIQUE','HAUTE','MOYENNE')),
    type_violation  TEXT NOT NULL,
    description     TEXT NOT NULL,
    plateforme      TEXT,
    territoire      TEXT,
    url             TEXT,
    statut          TEXT NOT NULL DEFAULT 'ouverte' CHECK(statut IN ('ouverte','en_cours','resolue','ignoree')),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_blocs_programme ON blocs_droits(programme);
CREATE INDEX IF NOT EXISTS idx_blocs_deal ON blocs_droits(deal_id);
CREATE INDEX IF NOT EXISTS idx_alertes_severite ON alertes(severite);
CREATE INDEX IF NOT EXISTS idx_alertes_statut ON alertes(statut);
CREATE INDEX IF NOT EXISTS idx_diffusions_programme ON diffusions_detectees(programme);
