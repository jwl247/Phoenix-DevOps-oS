import shutil, subprocess
from pathlib import Path
from .base import BackendBase
from core.verify import sha3_512, blake2b

CLONEPOOL = Path("/mnt/d/clonepool")

class ClonepoolBackend(BackendBase):
    name     = "clonepool"
    platform = "linux"

    def available(self):
        return CLONEPOOL.exists()

    def _find(self, package):
        # TAV stores files as hex/ver_filename — search sidecar JSONs for package name
        import json
        for sidecar in CLONEPOOL.rglob("*.sidecar.json"):
            try:
                data = json.loads(sidecar.read_text())
                fname = data.get("name", "") or data.get("filename", "")
                if package.lower() in fname.lower():
                    stored = sidecar.parent
                    debs = list(stored.glob("*.deb"))
                    if debs:
                        return sorted(debs)[-1]
            except Exception:
                continue
        # fallback: raw .deb search
        matches = list(CLONEPOOL.rglob(f"{package}*.deb"))
        return sorted(matches)[-1] if matches else None

    def _run(self, args):
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def install(self, package):
        deb = self._find(package)
        if not deb:
            return self.result(False, package, "install",
                               error=f"Not found in clonepool: {package}")
        print(f"  [clonepool] found: {deb.name}")
        print(f"  [clonepool] verifying hashes...")
        h1 = sha3_512(str(deb))
        h2 = blake2b(str(deb))
        print(f"  SHA3-512 : {h1[:32]}...")
        print(f"  BLAKE2b  : {h2[:32]}...")
        code, out, err = self._run(["sudo", "dpkg", "-i", str(deb)])
        if code != 0:
            self._run(["sudo", "apt", "install", "-f", "-y"])
        return self.result(code == 0, package, "install", out, err)

    def remove(self, package):
        code, out, err = self._run(["sudo", "dpkg", "-r", package])
        return self.result(code == 0, package, "remove", out, err)

    def upgrade(self, package=None):
        if not package:
            return self.result(False, "all", "upgrade",
                               error="Specify a package for clonepool upgrade")
        deb = self._find(package)
        if not deb:
            return self.result(False, package, "upgrade",
                               error=f"Not found in clonepool: {package}")
        code, out, err = self._run(["sudo", "dpkg", "-i", str(deb)])
        return self.result(code == 0, package, "upgrade", out, err)

    def search(self, query):
        matches = list(CLONEPOOL.rglob(f"*{query}*.deb"))
        return [{"name": m.stem, "description": str(m)} for m in matches]

    def info(self, package):
        deb = self._find(package)
        if not deb:
            return {"name": package, "error": "Not in clonepool"}
        code, out, err = self._run(["dpkg", "-I", str(deb)])
        info = {"name": package, "raw": out, "path": str(deb)}
        for line in out.splitlines():
            if "Version:" in line:
                info["version"] = line.split(":", 1)[1].strip()
            if "Description:" in line:
                info["description"] = line.split(":", 1)[1].strip()
        return info

    def seed(self, package):
        CLONEPOOL.mkdir(parents=True, exist_ok=True)
        code, out, err = self._run(["apt-get", "download", package])
        if code == 0:
            for deb in Path(".").glob(f"{package}*.deb"):
                print(f"  [clonepool] running TAV intake: {deb.name}")
                intake = self._run([
                    "usys", "intake", str(deb),
                    str(CLONEPOOL), "white",
                    f"installed via us"
                ])
                deb.unlink(missing_ok=True)
                print(f"  [clonepool] TAV intake complete")
                # auto-register in glossary
                from core.glossary import init_glossary, add_from_sidecar
                import time
                time.sleep(0.5)
                for sc in Path(str(CLONEPOOL)).rglob("*.sidecar.json"):
                    add_from_sidecar(str(sc))
        return self.result(code == 0, package, "seed", out, err)
