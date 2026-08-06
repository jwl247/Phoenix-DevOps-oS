import sqlite3
import os
from datetime import datetime
from pathlib import Path

DB_PATH = os.environ.get('UNITEDSYS_DB', str(Path.home() / '.catalog' / 'catalog.db'))
SCHEMA   = Path(__file__).parent.parent / 'db' / 'schema.sql'

def get_conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    conn.close()

def log_transaction(action, package, status, backend=None, duration_ms=None, error=None):
    conn = get_conn()
    conn.execute(
        'INSERT INTO transactions (action, package, status, backend, duration_ms, error) VALUES (?,?,?,?,?,?)',
        (action, package, status, backend, duration_ms, error)
    )
    conn.commit()
    conn.close()

def record_install(name, version, backend, platform, hash_sha3=None, hash_blake2=None, manifest=None):
    conn = get_conn()
    conn.execute('''
        INSERT INTO packages (name, version, backend, platform, hash_sha3, hash_blake2, manifest)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(name) DO UPDATE SET
            version=excluded.version,
            backend=excluded.backend,
            updated_at=CURRENT_TIMESTAMP
    ''', (name, version, backend, platform, hash_sha3, hash_blake2, manifest))
    conn.commit()
    conn.close()

def record_remove(name):
    conn = get_conn()
    conn.execute('DELETE FROM packages WHERE name=?', (name,))
    conn.commit()
    conn.close()

def get_package(name):
    conn = get_conn()
    row = conn.execute('SELECT * FROM packages WHERE name=?', (name,)).fetchone()
    conn.close()
    return dict(row) if row else None

def list_packages():
    conn = get_conn()
    rows = conn.execute('SELECT * FROM packages ORDER BY name').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def last_transaction():
    conn = get_conn()
    row = conn.execute('SELECT * FROM transactions ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    return dict(row) if row else None
