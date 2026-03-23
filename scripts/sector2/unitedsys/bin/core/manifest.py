import json
import os
from pathlib import Path

MANIFEST_DIR = Path(__file__).parent.parent / 'manifests'

def find_manifest(package: str) -> Path | None:
    for ext in ('.toml', '.json'):
        p = MANIFEST_DIR / f'{package}{ext}'
        if p.exists():
            return p
    return None

def parse_toml(path: Path) -> dict:
    data = {}
    section = None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
            data[section] = {}
            continue
        if '=' in line:
            key, _, val = line.partition('=')
            key = key.strip()
            val = val.strip().strip('"')
            if section:
                data[section][key] = val
            else:
                data[key] = val
    return data

def parse_json(path: Path) -> dict:
    return json.loads(path.read_text())

def load(package: str) -> dict | None:
    path = find_manifest(package)
    if not path:
        return None
    if path.suffix == '.toml':
        return parse_toml(path)
    return parse_json(path)

def get_backend_name(manifest: dict, backend: str) -> str:
    backends = manifest.get('backends', {})
    return backends.get(backend, manifest.get('package', {}).get('name', ''))

def get_hooks(manifest: dict) -> dict:
    return manifest.get('hooks', {
        'pre_install' : '',
        'post_install': '',
        'pre_remove'  : '',
        'post_remove' : '',
    })

def get_hashes(manifest: dict) -> dict:
    src = manifest.get('source', {})
    return {
        'sha3_512': src.get('sha3_512', ''),
        'blake2b' : src.get('blake2b',  ''),
    }

def list_manifests() -> list:
    results = []
    for f in MANIFEST_DIR.glob('*'):
        if f.suffix in ('.toml', '.json'):
            results.append(f.stem)
    return sorted(results)
