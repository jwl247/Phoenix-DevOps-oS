-- UnitedSys catalog schema
-- Compatible with ~/.catalog/catalog.db

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS packages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    version      TEXT,
    backend      TEXT,
    platform     TEXT,
    installed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME,
    hash_sha3    TEXT,
    hash_blake2  TEXT,
    manifest     TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,
    package     TEXT NOT NULL,
    status      TEXT NOT NULL,
    backend     TEXT,
    duration_ms INTEGER,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS deps (
    package    TEXT NOT NULL,
    depends_on TEXT NOT NULL,
    PRIMARY KEY (package, depends_on)
);

CREATE TABLE IF NOT EXISTS backends (
    name        TEXT PRIMARY KEY,
    platform    TEXT,
    available   INTEGER DEFAULT 0,
    last_check  DATETIME
);

CREATE INDEX IF NOT EXISTS idx_packages_name ON packages(name);
CREATE INDEX IF NOT EXISTS idx_transactions_package ON transactions(package);
CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp);
