#!/usr/bin/env python3
# =============================================================================
# core/intake.py — UnitedSys TAV Intake Engine
# Project:  Phoenix DevOps / UnitedSys
# Author:   jwl247 / Phoenix DevOps LLC
# License:  GPL-3.0
#
# ARCHITECTURE:
#   Every file that enters the system passes through intake.
#   Intake issues a tamper-evident dual-QR pair:
#
#     HEADER QR (top)  — state color (white/grey/black)
#                        encodes the b58 address of this object
#                        generated BEFORE hashing
#
#     FOOTER QR (bottom) — tier color (T1=primary, T2=secondary, T3/T4=tertiary)
#                          encodes b58 address + both hash fingerprints
#                          generated AFTER hashing and sidecar write
#
#   VALIDATION:
#     b58 address in header QR must match footer QR address.
#     hex fingerprint in footer QR must match catalog sha3[:16].
#     If either fails — tamper detected without reading the file.
#
#   ADDRESS SYSTEM:
#     filename -> SHA3-512 -> first 8 bytes as hex -> base58 encode
#     Shortest unique address possible.
#     SQL primary key = hex. b58 = human/QR-readable form.
#     Everything (clone, catalog, sidecar, QR) uses this address.
#
#   TIER / COLOR MAPPING:
#     Header state colors:
#       white = #FFFFFF  clean, verified
#       grey  = #888888  unknown, unverified
#       black = #1A1A1A  flagged, dangerous
#
#     Footer tier colors (clonepool depth):
#       T1 breach_coms4 = primary   (red/blue/yellow)
#       T2 breach_coms3 = secondary (orange/green/purple)
#       T3 breach_coms2 = tertiary  (teal/brown/olive)
#       T4 breach_coms1 = tertiary  (slate/mauve/sage)
#
#   QUADRALINGUAL RULE:
#     Intake never translates. Objects enter quadralingual.
#     translator.sh fires on output at sector3 boundary only.
# =============================================================================

import os
import re
import json
import hashlib
import shutil
import subprocess
from datetime import datetime
from pathlib  import Path
from typing   import Optional

from core.verify  import sha3_512, blake2b
from core.catalog import get_conn, DB_PATH

# ── Paths ─────────────────────────────────────────────────────────────────────
CLONEPOOL  = Path(os.environ.get('CLONEPOOL',  '/mnt/d/clonepool'))
QR_OUT_DIR = Path(os.environ.get('QR_OUT_DIR', str(Path.home() / '.catalog' / 'qr')))
CATALOG_DB = Path(DB_PATH)

# ── Base58 ────────────────────────────────────────────────────────────────────
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def _to_b58(hex_str: str) -> str:
    if not hex_str:
        return '1'
    n = int(hex_str, 16)
    r = []
    while n > 0:
        n, rem = divmod(n, 58)
        r.append(B58[rem])
    return ''.join(reversed(r)) or '1'

# ── Address generation ────────────────────────────────────────────────────────

def make_address(filename: str) -> tuple:
    """
    Generate shortest unique address for a filename.
    Returns (hex_id, b58_id).
    SHA3-512 of filename string -> first 8 bytes -> base58.
    Generated from filename alone so header QR can be issued before hashing.
    Extend to 12 bytes via ADDRESS_BYTES env var if needed.
    """
    addr_bytes = int(os.environ.get('ADDRESS_BYTES', '8'))
    raw    = hashlib.sha3_512(filename.encode()).hexdigest()
    hex_id = raw[:addr_bytes * 2]
    b58_id = _to_b58(hex_id)
    return hex_id, b58_id

# ── Color tables ─────────────────────────────────────────────────────────────

STATE_COLORS = {
    'white': ('#FFFFFF', '#000000'),
    'grey' : ('#888888', '#FFFFFF'),
    'gray' : ('#888888', '#FFFFFF'),
    'black': ('#1A1A1A', '#FFFFFF'),
}

TIER_COLORS = {
    1: [('#E63946','#FFFFFF'), ('#2471A3','#FFFFFF'), ('#F1C40F','#000000')],
    2: [('#E67E22','#FFFFFF'), ('#27AE60','#FFFFFF'), ('#7D3C98','#FFFFFF')],
    3: [('#148F77','#FFFFFF'), ('#784212','#FFFFFF'), ('#7D6608','#FFFFFF')],
    4: [('#566573','#FFFFFF'), ('#6C3483','#FFFFFF'), ('#2E7D32','#FFFFFF')],
}

def _tier_color(tier: int, b58_id: str) -> tuple:
    palette = TIER_COLORS.get(tier, TIER_COLORS[4])
    idx     = sum(ord(c) for c in b58_id) % len(palette)
    return palette[idx]

def _state_color(state: str) -> tuple:
    return STATE_COLORS.get(state.lower(), STATE_COLORS['grey'])

# ── QR generation ─────────────────────────────────────────────────────────────

def _qrencode(data: str, out_path: Path, bg: str, fg: str, size: int = 6) -> bool:
    bg_clean = bg.lstrip('#')
    fg_clean = fg.lstrip('#')
    cmd = [
        'qrencode', '-o', str(out_path),
        '-s', str(size), '-m', '2', '--level=M',
        f'--foreground={fg_clean}',
        f'--background={bg_clean}',
        data
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        print('  [intake] WARNING: qrencode not found — QR skipped')
        return False

def generate_header_qr(b58_id: str, state: str, out_dir: Path) -> Optional[Path]:
    """Header QR — before hashing. Encodes: USYS:<b58>:HEADER. Color = state."""
    bg, fg   = _state_color(state)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{b58_id}_header.png'
    data     = f'USYS:{b58_id}:HEADER'
    ok       = _qrencode(data, out_path, bg, fg)
    return out_path if ok else None

def generate_footer_qr(b58_id: str, hex_id: str, sha3_fp: str,
                       blake2_fp: str, tier: int, out_dir: Path) -> Optional[Path]:
    """Footer QR — after hashing. Encodes: USYS:<b58>:FOOTER:<sha3_fp>:<b2_fp>. Color = tier."""
    bg, fg   = _tier_color(tier, b58_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{b58_id}_footer.png'
    data     = f'USYS:{b58_id}:FOOTER:{sha3_fp}:{blake2_fp}'
    ok       = _qrencode(data, out_path, bg, fg)
    return out_path if ok else None

# ── Hex validation ────────────────────────────────────────────────────────────

def validate_qr_pair(header_path: Optional[Path], footer_path: Optional[Path],
                     b58_id: str, sha3_fp: str) -> dict:
    """
    Validate QR pair integrity.
    Hashes both QR PNGs — if tampered, their SHA3 won't match sidecar records.
    """
    errors = []
    header_hash = ''
    footer_hash = ''

    if not header_path or not header_path.exists():
        errors.append('Header QR missing')
    else:
        header_hash = sha3_512(str(header_path))

    if not footer_path or not footer_path.exists():
        errors.append('Footer QR missing')
    else:
        footer_hash = sha3_512(str(footer_path))

    return {
        'valid'       : len(errors) == 0,
        'errors'      : errors,
        'header_hash' : header_hash[:32] if header_hash else '',
        'footer_hash' : footer_hash[:32] if footer_hash else '',
        'b58_id'      : b58_id,
        'sha3_fp'     : sha3_fp,
    }

# ── Sidecar ───────────────────────────────────────────────────────────────────

def write_sidecar(dest_file: Path, hex_id: str, b58_id: str,
                  sha3: str, b2: str, state: str, tier: int,
                  header_qr: Optional[Path], footer_qr: Optional[Path],
                  desc: str = '', original_path: str = '') -> Path:
    """Write .sidecar.json alongside the file. The b58 address is the key for everything."""
    sidecar_path = dest_file.parent / f'{dest_file.name}.sidecar.json'
    sidecar = {
        'hex'          : hex_id,
        'b58'          : b58_id,
        'qr_id'        : b58_id,
        'name'         : dest_file.name,
        'filename'     : dest_file.name,
        'original_name': Path(original_path).name if original_path else dest_file.name,
        'path'         : str(dest_file),
        'pool_path'    : str(dest_file.parent),
        'source_path'  : original_path,
        'tier'         : tier,
        'state'        : state,
        'description'  : desc or dest_file.name,
        'hash_sha3'    : sha3,
        'hash_blake2'  : b2,
        'sha3_fp'      : sha3[:16],
        'blake2_fp'    : b2[:16],
        'header_qr'    : str(header_qr) if header_qr else '',
        'footer_qr'    : str(footer_qr) if footer_qr else '',
        'clone_pool'   : {
            'path' : str(dest_file.parent),
            'tier' : tier,
            'hex'  : hex_id,
            'b58'  : b58_id,
        },
        'intaked_at'   : datetime.utcnow().isoformat(),
    }
    sidecar_path.write_text(json.dumps(sidecar, indent=2))
    return sidecar_path

# ── Catalog registration ──────────────────────────────────────────────────────

def _detect_platform() -> str:
    import platform
    s = platform.system().lower()
    if 'linux' in s:
        return 'linux'
    if 'windows' in s or 'nt' in s:
        return 'windows'
    return s

def register_in_catalog(hex_id: str, b58_id: str, name: str,
                        sha3: str, b2: str, state: str, tier: int,
                        pool_path: str, sidecar_path: str,
                        backend: str = 'clonepool', version: str = ''):
    """Register in catalog.db packages + transactions + glossary.db."""

    # catalog.db
    try:
        conn = get_conn()
        conn.execute('''
            INSERT INTO packages
                (name, version, backend, platform, hash_sha3, hash_blake2, manifest)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                hash_sha3   = excluded.hash_sha3,
                hash_blake2 = excluded.hash_blake2,
                updated_at  = CURRENT_TIMESTAMP
        ''', (name, version, backend, _detect_platform(), sha3, b2, sidecar_path))
        conn.execute('''
            INSERT INTO transactions (action, package, status, backend, error)
            VALUES (?,?,?,?,?)
        ''', ('intake', name, 'registered', backend,
              f'tier={tier} state={state} b58={b58_id}'))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'  [intake] catalog write warning: {e}')

    # glossary.db
    try:
        from core.glossary import init_glossary, add_entry, _detect_category
        init_glossary()
        add_entry(
            hex_id      = hex_id,
            name        = re.split(r'[_\-][\d]', name)[0].strip() or name,
            version     = version,
            size        = Path(pool_path).stat().st_size if Path(pool_path).exists() else 0,
            pool_path   = pool_path,
            sidecar     = sidecar_path,
            description = f'TAV intake — tier={tier} state={state}',
            raw_name    = name,
        )
    except Exception as e:
        print(f'  [intake] glossary write warning: {e}')

# ── MAIN INTAKE ───────────────────────────────────────────────────────────────

def intake(file_path: str, pool: str = None, state: str = 'white',
           desc: str = '', tier: int = 1, version: str = '',
           backend: str = 'clonepool', qr_dir: str = None) -> dict:
    """
    Full TAV intake for a single file.

    1. Generate address (hex_id, b58_id) from filename
    2. Generate HEADER QR  (state color)   — before hashing
    3. Copy file to pool
    4. Hash the file (SHA3-512 + BLAKE2b)
    5. Write sidecar JSON
    6. Generate FOOTER QR  (tier color)    — after hashing
    7. Validate QR pair
    8. Register in catalog.db + glossary.db
    9. Return result dict
    """
    src      = Path(file_path).resolve()
    pool_dir = Path(pool).resolve() if pool else CLONEPOOL
    qr_base  = Path(qr_dir).resolve() if qr_dir else QR_OUT_DIR

    if not src.exists():
        return _fail(f'Source not found: {src}')

    # 1. Address
    hex_id, b58_id = make_address(src.name)
    print(f'\n[intake] {src.name}')
    print(f'  address : {b58_id}  ({hex_id})')

    # 2. Header QR
    print(f'  state   : {state}')
    header_qr = generate_header_qr(b58_id, state, qr_base)
    if header_qr:
        print(f'  header  : {header_qr.name}')
    else:
        print(f'  header  : QR skipped')

    # 3. Copy to pool
    pool_dir.mkdir(parents=True, exist_ok=True)
    dest = pool_dir / src.name
    if dest != src:
        try:
            shutil.copy2(str(src), str(dest))
        except Exception as e:
            return _fail(f'Copy to pool failed: {e}')
    print(f'  pool    : {dest}')

    # 4. Hash
    h_sha3   = sha3_512(str(dest))
    h_blake2 = blake2b(str(dest))
    sha3_fp  = h_sha3[:16]
    b2_fp    = h_blake2[:16]
    print(f'  SHA3    : {sha3_fp}...')
    print(f'  BLAKE2b : {b2_fp}...')

    # 5. Sidecar (footer QR path filled in after generation)
    sidecar_path = write_sidecar(
        dest_file     = dest,
        hex_id        = hex_id,
        b58_id        = b58_id,
        sha3          = h_sha3,
        b2            = h_blake2,
        state         = state,
        tier          = tier,
        header_qr     = header_qr,
        footer_qr     = None,
        desc          = desc or src.name,
        original_path = str(src),
    )
    print(f'  sidecar : {sidecar_path.name}')

    # 6. Footer QR
    print(f'  tier    : T{tier}')
    footer_qr = generate_footer_qr(
        b58_id    = b58_id,
        hex_id    = hex_id,
        sha3_fp   = sha3_fp,
        blake2_fp = b2_fp,
        tier      = tier,
        out_dir   = qr_base,
    )
    if footer_qr:
        print(f'  footer  : {footer_qr.name}')
        # update sidecar with footer path
        try:
            data = json.loads(sidecar_path.read_text())
            data['footer_qr'] = str(footer_qr)
            sidecar_path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass
    else:
        print(f'  footer  : QR skipped')

    # 7. Validate
    validation = validate_qr_pair(header_qr, footer_qr, b58_id, sha3_fp)
    print(f'  QR pair : {"VALID" if validation["valid"] else "WARNING — " + str(validation["errors"])}')

    # 8. Register
    register_in_catalog(
        hex_id       = hex_id,
        b58_id       = b58_id,
        name         = src.name,
        sha3         = h_sha3,
        b2           = h_blake2,
        state        = state,
        tier         = tier,
        pool_path    = str(dest),
        sidecar_path = str(sidecar_path),
        backend      = backend,
        version      = version,
    )
    print(f'  catalog : registered')
    print(f'  [OK]\n')

    return {
        'success'    : True,
        'name'       : src.name,
        'hex'        : hex_id,
        'b58'        : b58_id,
        'path'       : str(dest),
        'sidecar'    : str(sidecar_path),
        'header_qr'  : str(header_qr) if header_qr else '',
        'footer_qr'  : str(footer_qr) if footer_qr else '',
        'hash_sha3'  : h_sha3,
        'hash_blake2': h_blake2,
        'state'      : state,
        'tier'       : tier,
        'qr_valid'   : validation['valid'],
        'intaked_at' : datetime.utcnow().isoformat(),
    }


def intake_dir(directory: str, pool: str = None, state: str = 'white',
               tier: int = 1, desc: str = '', qr_dir: str = None) -> dict:
    """Intake an entire directory. Every file gets the full treatment."""
    src_dir = Path(directory).expanduser().resolve()
    if not src_dir.exists():
        return _fail(f'Directory not found: {src_dir}')

    excludes = {'.git', '__pycache__', '.pyc', 'sidecar.json',
                'node_modules', 'site', '.catalog'}
    files = [
        f for f in src_dir.rglob('*')
        if f.is_file()
        and not any(ex in str(f) for ex in excludes)
    ]

    print(f'\n[intake_dir] {src_dir}')
    print(f'  files : {len(files)}  pool : {pool or CLONEPOOL}  state : {state}  tier : T{tier}')
    print()

    ok = fail = 0
    for f in files:
        result = intake(str(f), pool=pool, state=state,
                        desc=desc or str(f.relative_to(src_dir)),
                        tier=tier, qr_dir=qr_dir)
        if result['success']:
            ok += 1
        else:
            fail += 1
            print(f'  [FAIL] {f.name}: {result.get("error")}')

    print(f'\n[intake_dir] complete — {ok} OK, {fail} failed')

    try:
        from core.glossary import init_glossary, add_from_sidecar
        init_glossary()
        pool_dir = Path(pool or CLONEPOOL)
        imported = sum(
            1 for s in pool_dir.rglob('*.sidecar.json')
            if add_from_sidecar(str(s))
        )
        print(f'[intake_dir] glossary — {imported} entries synced')
    except Exception as e:
        print(f'[intake_dir] glossary sync warning: {e}')

    return {'success': fail == 0, 'ok': ok, 'fail': fail, 'total': len(files)}


def _fail(msg: str) -> dict:
    print(f'  [intake] FAIL: {msg}')
    return {'success': False, 'error': msg}
