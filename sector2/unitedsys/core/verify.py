import hashlib
from pathlib import Path

def sha3_512(path: str) -> str:
    h = hashlib.sha3_512()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def blake2b(path: str) -> str:
    h = hashlib.blake2b()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def verify(path: str, expected_sha3: str = None, expected_blake2: str = None) -> dict:
    result = {
        'path'    : path,
        'sha3_512': sha3_512(path),
        'blake2b' : blake2b(path),
        'passed'  : True,
        'errors'  : []
    }
    if expected_sha3 and result['sha3_512'] != expected_sha3:
        result['passed'] = False
        result['errors'].append('SHA3-512 mismatch')
    if expected_blake2 and result['blake2b'] != expected_blake2:
        result['passed'] = False
        result['errors'].append('BLAKE2b mismatch')
    return result
