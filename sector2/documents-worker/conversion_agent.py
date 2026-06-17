#!/usr/bin/env python3
"""
conversion_agent.py — LibreOffice Headless Conversion Agent
Runs on phoenix-ext. Polls documents-worker job queue, converts documents
using LibreOffice as a process (not an app), forges the result as a new
Phoenix document (new TAV, parent_tav = source).

Install:   sudo apt install libreoffice-nogui
Run:       python3 conversion_agent.py
Systemd:   see sector3/services/ — phoenix-conversion-agent.service

The document converts itself. LibreOffice is the process, not the app.
Phoenix DevOps OS | jwl247 | GPL v3
"""

import json
import os
import sys
import time
import base64
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

WORKER_URL   = os.environ.get("DOCS_WORKER_URL",  "https://documents-worker.phoenix-jwl.workers.dev")
PHOENIX_AUTH = os.environ.get("PHOENIX_AUTH",      "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_S", "10"))
WORK_DIR     = Path(os.environ.get("CONV_WORK_DIR", "/tmp/phoenix_conversions"))
LOG_FILE     = Path(os.environ.get("PHOENIX_AUDIT", "/var/log/phoenix/audit.log"))
LIBRE_BIN    = shutil.which("libreoffice") or shutil.which("soffice") or "/usr/bin/libreoffice"

# LibreOffice filter map: target MIME → --convert-to argument
LIBRE_FILTERS = {
    "application/pdf":   "pdf",
    "text/html":         "html",
    "text/plain":        "txt",
    "text/csv":          "csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.oasis.opendocument.presentation": "odp",
}


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str, level: str = "INFO"):
    ts  = datetime.now(timezone.utc).isoformat()
    line = json.dumps({"ts": ts, "op": "conversion_agent", "level": level, "msg": msg})
    print(f"[{ts}] [{level}] {msg}", flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Worker HTTP helpers ───────────────────────────────────────────────────────

def _worker_get(path: str) -> dict | None:
    url = f"{WORKER_URL}{path}"
    req = urllib.request.Request(url, headers={
        "X-Phoenix-Auth": PHOENIX_AUTH, "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        _log(f"GET {path} → HTTP {e.code}: {e.read()}", "ERROR")
        return None
    except Exception as e:
        _log(f"GET {path} → {e}", "ERROR")
        return None


def _worker_post(path: str, body: dict, timeout: int = 60) -> dict:
    url  = f"{WORKER_URL}{path}"
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data, method="POST", headers={
        "X-Phoenix-Auth": PHOENIX_AUTH, "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_err = e.read().decode(errors="replace")
        _log(f"POST {path} → HTTP {e.code}: {body_err}", "ERROR")
        return {"error": body_err}
    except Exception as e:
        _log(f"POST {path} → {e}", "ERROR")
        return {"error": str(e)}


def _worker_get_raw(path: str) -> bytes | None:
    url = f"{WORKER_URL}{path}"
    req = urllib.request.Request(url, headers={"X-Phoenix-Auth": PHOENIX_AUTH})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except Exception as e:
        _log(f"GET raw {path} → {e}", "ERROR")
        return None


# ── Poll job queue ────────────────────────────────────────────────────────────

def poll_jobs() -> list[dict]:
    r = _worker_get("/jobs")
    if r and "jobs" in r:
        return r["jobs"]
    return []


# ── LibreOffice conversion (headless process) ─────────────────────────────────

def convert_with_libreoffice(source_path: Path, target_mime: str, out_dir: Path) -> Path | None:
    filter_arg = LIBRE_FILTERS.get(target_mime)
    if not filter_arg:
        _log(f"no LibreOffice filter for {target_mime}", "ERROR")
        return None

    if not Path(LIBRE_BIN).exists():
        _log(f"LibreOffice not found at {LIBRE_BIN}. Install: sudo apt install libreoffice-nogui", "ERROR")
        return None

    cmd = [
        LIBRE_BIN,
        "--headless",
        "--norestore",
        "--nofirststartwizard",
        "--convert-to", filter_arg,
        "--outdir", str(out_dir),
        str(source_path),
    ]

    _log(f"libreoffice --headless --convert-to {filter_arg} {source_path.name}")
    t0 = time.perf_counter()

    try:
        r = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=120,
            env={**os.environ, "HOME": str(out_dir)},  # isolate LibreOffice profile
        )
        elapsed = time.perf_counter() - t0

        if r.returncode != 0:
            _log(f"LibreOffice failed (exit {r.returncode}): {r.stderr}", "ERROR")
            return None

        # LibreOffice outputs to out_dir with the same stem, different extension
        ext    = LIBRE_FILTERS[target_mime]
        result = out_dir / f"{source_path.stem}.{ext}"
        if not result.exists():
            # Search for any output file (sometimes LibreOffice changes filename)
            candidates = list(out_dir.glob(f"*.{ext}"))
            if not candidates:
                _log(f"LibreOffice produced no output in {out_dir}", "ERROR")
                return None
            result = candidates[0]

        _log(f"converted {source_path.name} → {result.name} in {elapsed:.2f}s ({result.stat().st_size} bytes)")
        return result

    except subprocess.TimeoutExpired:
        _log("LibreOffice timed out after 120s", "ERROR")
        return None
    except Exception as e:
        _log(f"LibreOffice error: {e}", "ERROR")
        return None


# ── Process one job ───────────────────────────────────────────────────────────

def process_job(job: dict) -> bool:
    job_id      = job["id"]
    source_tav  = job["source_tav"]
    source_r2   = job["source_r2"]
    source_mime = job["source_mime"]
    target_mime = job["target_format"]
    target_ext  = job["target_ext"]
    owner       = job["owner"]

    _log(f"job {job_id}: {source_tav} → {target_mime}")

    # Mark as running
    _worker_post(f"/jobs/{job_id}/running", {})

    with tempfile.TemporaryDirectory(prefix="phoenix_conv_", dir=WORK_DIR) as tmp:
        tmp_path = Path(tmp)

        # 1. Fetch source content from worker
        raw = _worker_get_raw(f"/doc/{source_tav}")
        if not raw:
            _worker_post(f"/jobs/{job_id}/fail", {"error": "could not fetch source content"})
            return False

        # 2. Determine source extension
        src_ext = {
            "text/markdown":    "md",   "text/plain": "txt",
            "text/html":        "html", "text/csv":   "csv",
            "application/json": "json",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
            "application/vnd.oasis.opendocument.text": "odt",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
            "application/vnd.oasis.opendocument.spreadsheet": "ods",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
            "application/vnd.oasis.opendocument.presentation": "odp",
        }.get(source_mime, "bin")

        src_file = tmp_path / f"source.{src_ext}"
        src_file.write_bytes(raw)

        # 3. Run LibreOffice headless
        result_file = convert_with_libreoffice(src_file, target_mime, tmp_path)
        if not result_file:
            _worker_post(f"/jobs/{job_id}/fail", {"error": "LibreOffice conversion failed"})
            return False

        # 4. Forge the result as a new Phoenix document
        content_b64  = base64.b64encode(result_file.read_bytes()).decode()
        result_filename = f"{Path(source_tav).stem}.{target_ext}"

        # Inherit manifest from source doc (capabilities can only equal or decrease)
        src_meta = _worker_get(f"/doc/{source_tav}/meta") or {}
        src_manifest = src_meta.get("manifest", {})

        # Build child manifest: only keep compatible capabilities
        child_manifest = {
            "can_read":     src_manifest.get("can_read", True),
            "can_convert":  [],  # conversion of a conversion not auto-inherited
            "can_execute":  False,
            "can_version":  src_manifest.get("can_version", True),
            "can_review":   src_manifest.get("can_review", False),
            "can_index":    src_manifest.get("can_index", True),
            "can_transmit": src_manifest.get("can_transmit", []),
            "can_share":    src_manifest.get("can_share", []),
            "life_first":   src_manifest.get("life_first", False),
        }

        forge_payload = {
            "filename":     result_filename,
            "content_b64":  content_b64,
            "mime_type":    target_mime,
            "owner":        owner,
            "title":        f"{src_meta.get('title', source_tav)} [{target_ext.upper()}]",
            "description":  f"LibreOffice conversion from {source_mime} → {target_mime}",
            "sector":       src_meta.get("sector"),
            "tags":         src_meta.get("tags", []) + ["conversion", target_ext],
            "privacy":      src_meta.get("privacy", "private"),
            "classification": src_meta.get("classification", "internal"),
            "manifest":     child_manifest,
            "conversion_of":  source_tav,
            "conversion_fmt": target_mime,
            "encrypt":      bool(src_meta.get("encrypted")),
        }

        forge_result = _worker_post("/doc/forge", forge_payload, timeout=120)
        if "error" in forge_result:
            _worker_post(f"/jobs/{job_id}/fail", {"error": f"forge failed: {forge_result['error']}"})
            return False

        result_tav = forge_result.get("tav")
        _log(f"job {job_id}: forged result → {result_tav}")

        # 5. Mark job complete
        _worker_post(f"/jobs/{job_id}/complete", {"result_tav": result_tav})
        return True


# ── Main poll loop ────────────────────────────────────────────────────────────

def main():
    if not PHOENIX_AUTH:
        print("ERROR: PHOENIX_AUTH env var required")
        sys.exit(1)

    if not Path(LIBRE_BIN).exists():
        print(f"WARNING: LibreOffice not found at {LIBRE_BIN}")
        print("Install: sudo apt install libreoffice-nogui")

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    _log(f"conversion_agent started — polling {WORKER_URL}/jobs every {POLL_INTERVAL}s")
    _log(f"LibreOffice: {LIBRE_BIN}")

    while True:
        try:
            jobs = poll_jobs()
            if jobs:
                _log(f"{len(jobs)} job(s) in queue")
                for job in jobs:
                    try:
                        process_job(job)
                    except Exception as e:
                        _log(f"job {job.get('id')} unhandled error: {e}", "ERROR")
                        try:
                            _worker_post(f"/jobs/{job['id']}/fail", {"error": str(e)})
                        except Exception:
                            pass
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            _log("stopped")
            break
        except Exception as e:
            _log(f"poll error: {e}", "ERROR")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
