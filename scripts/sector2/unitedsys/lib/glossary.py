
B58_CHARS = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def hex_to_b58(hex_str):
    if not hex_str:
        return ''
    n = int(hex_str, 16)
    result = []
    while n > 0:
        n, r = divmod(n, 58)
        result.append(B58_CHARS[r])
    return ''.join(reversed(result)) or '1'

def b58_to_hex(b58_str):
    n = 0
    for c in b58_str:
        n = n * 58 + B58_CHARS.index(c)
    h = hex(n)[2:]
    return h if len(h) % 2 == 0 else '0' + h

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from core.catalog import get_conn, DB_PATH

def init_glossary():
    conn = get_conn()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS categories (
            hex         TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT ""
        );

        INSERT OR IGNORE INTO categories (hex, name, description) VALUES
            ("73797374656d",       "system",    "OS tools, daemons, kernel-level"),
            ("6e6574776f726b",     "network",   "VPN, firewall, comms, protocols"),
            ("7365637572697479",   "security",  "auth, hashing, verification, hardening"),
            ("73746f72616765",     "storage",   "clonepool, vaults, drives, filesystems"),
            ("72756e74696d65",     "runtime",   "interpreters, language runtimes"),
            ("746f6f6c73",         "tools",     "CLI utilities, dev tools, helpers"),
            ("6672616d65776f726b", "framework", "Phoenix, Helix, Propagator components"),
            ("6461746162617365",   "database",  "SQLite, D1, catalog, schemas"),
            ("73637269707473",     "scripts",   "shell scripts, automation, wrappers"),
            ("6d65646961",         "media",     "images, QR codes, visual assets"),
            ("74797065",           "type",      "file type classification"),
            ("756e6b6e6f776e",     "unknown",   "uncategorized, needs review");

        CREATE TABLE IF NOT EXISTS glossary (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            hex          TEXT NOT NULL UNIQUE,
            name         TEXT NOT NULL,
            category_hex TEXT REFERENCES categories(hex),
            description  TEXT DEFAULT "",
            state        TEXT DEFAULT "white",
            version      TEXT,
            platform     TEXT,
            backend      TEXT,
            size         INTEGER,
            pool_path    TEXT,
            sidecar      TEXT,
            amended      INTEGER DEFAULT 0,
            intaked_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            grace_until  DATETIME GENERATED ALWAYS AS
                         (datetime(intaked_at, "+3 days")) VIRTUAL,
            evicted_at   DATETIME
        );

        CREATE INDEX IF NOT EXISTS idx_glossary_name     ON glossary(name);
        CREATE INDEX IF NOT EXISTS idx_glossary_hex      ON glossary(hex);
        CREATE INDEX IF NOT EXISTS idx_glossary_state    ON glossary(state);
        CREATE INDEX IF NOT EXISTS idx_glossary_category ON glossary(category_hex);

        CREATE VIEW IF NOT EXISTS glossary_view AS
        SELECT
            g.hex,
            g.name,
            g.hex        AS qr_id,
            c.name       AS category,
            c.hex        AS category_hex,
            g.state,
            g.description,
            g.version,
            g.platform,
            g.backend,
            g.amended,
            g.grace_until,
            g.intaked_at,
            g.evicted_at
        FROM glossary g
        LEFT JOIN categories c ON c.hex = g.category_hex;
    ''')
    conn.commit()
    conn.close()

def add_entry(hex_id, name, version=None, platform=None, backend=None,
              size=None, pool_path=None, sidecar=None, description='', raw_name=None):
    """Add or update a glossary entry from sidecar/catalog data"""
    category_hex = _detect_category(raw_name or name, sidecar)
    b58 = hex_to_b58(hex_id)
    conn = get_conn()
    conn.execute('''
        INSERT INTO glossary
            (hex, b58, name, category_hex, description, version, platform, backend, size, pool_path, sidecar)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(hex) DO UPDATE SET
            name=excluded.name,
            b58=excluded.b58,
            version=excluded.version,
            platform=excluded.platform,
            backend=excluded.backend
    ''', (hex_id, b58, name, category_hex, description, version, platform, backend, size, pool_path, sidecar))
    conn.commit()
    conn.close()

def add_from_sidecar(sidecar_path):
    """Parse a TAV sidecar JSON and create glossary entry"""
    try:
        data = json.loads(Path(sidecar_path).read_text())
        hex_id  = data.get('hex_name') or data.get('hex', '')
        raw     = data.get('original_name') or data.get('name', '')
        # strip version/arch/ext: wget_1.25.0-2_amd64.deb -> wget
        import re
        name    = re.split(r'[_\-][\d]', raw)[0].strip()
        if not name:
            name = raw
        # detect category from raw name before stripping
        _raw_for_cat = raw
        version = data.get('version', '')
        size    = data.get('size_bytes') or data.get('size', 0)
        pool    = (data.get('clone_pool') or {}).get('path', '') or data.get('pool', '')
        add_entry(
            hex_id      = hex_id,
            name        = name,
            version     = version,
            size        = size,
            pool_path   = pool,
            sidecar     = sidecar_path,
            description = 'Auto-generated from TAV intake — amend within 3 days',
            raw_name    = _raw_for_cat
        )
        return True
    except Exception as e:
        print(f'  [glossary] sidecar parse failed: {e}')
        return False

def amend(identifier, description, category=None):
    """Amend a glossary entry by name or hex"""
    conn = get_conn()
    cat_hex = None
    if category:
        row = conn.execute(
            'SELECT hex FROM categories WHERE name=? OR hex=?',
            (category, category)
        ).fetchone()
        if row:
            cat_hex = row['hex']

    if cat_hex:
        conn.execute('''
            UPDATE glossary SET description=?, category_hex=?, amended=1
            WHERE hex=? OR name=?
        ''', (description, cat_hex, identifier, identifier))
    else:
        conn.execute('''
            UPDATE glossary SET description=?, amended=1
            WHERE hex=? OR name=?
        ''', (description, identifier, identifier))
    conn.commit()
    conn.close()

def remove_entry(identifier):
    """Remove entry by name or hex"""
    conn = get_conn()
    conn.execute('DELETE FROM glossary WHERE hex=? OR name=?', (identifier, identifier))
    conn.commit()
    conn.close()

def get_entry(identifier):
    """Lookup by name, hex, or b58"""
    conn = get_conn()
    row = conn.execute(
        'SELECT * FROM glossary_view WHERE hex=? OR name=? OR b58=?',
        (identifier, identifier, identifier)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def list_entries(state=None, category=None):
    conn = get_conn()
    query = 'SELECT * FROM glossary_view'
    params = []
    clauses = []
    if state:
        clauses.append('state=?')
        params.append(state)
    if category:
        clauses.append('(category=? OR category_hex=?)')
        params.extend([category, category])
    if clauses:
        query += ' WHERE ' + ' AND '.join(clauses)
    query += ' ORDER BY name'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def check_evictions():
    """Evict unamended entries past grace period"""
    conn = get_conn()
    expired = conn.execute('''
        SELECT hex, name, grace_until FROM glossary
        WHERE amended=0
        AND datetime("now") > grace_until
        AND evicted_at IS NULL
    ''').fetchall()
    evicted = []
    for row in expired:
        conn.execute('''
            UPDATE glossary SET
                state="evicted",
                evicted_at=datetime("now")
            WHERE hex=?
        ''', (row['hex'],))
        evicted.append(dict(row))
    conn.commit()
    conn.close()
    return evicted

def list_categories():
    conn = get_conn()
    rows = conn.execute('SELECT * FROM categories ORDER BY name').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def _detect_category(name, sidecar_path=None):
    """Auto-detect category hex from name/extension"""
    n = name.lower()
    if any(x in n for x in ('.sh', '.zsh', '.bash')):
        return '73637269707473'   # scripts
    if any(x in n for x in ('.py',)):
        return '72756e74696d65'   # runtime
    if any(x in n for x in ('.db', '.sql', 'd1')):
        return '6461746162617365' # database
    if any(x in n for x in ('.png', '.jpg', '.qr')):
        return '6d65646961'       # media
    if any(x in n for x in ('.deb', 'apt', 'dpkg')):
        return '73797374656d'     # system
    if any(x in n for x in ('helix', 'phoenix', 'frank', 'propagator')):
        return '6672616d65776f726b' # framework
    return '756e6b6e6f776e'       # unknown
