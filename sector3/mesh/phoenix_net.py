#!/usr/bin/env python3
"""
phoenix_net.py — Phoenix Mesh: our own virtual network (Nebula), one command per step
Phoenix DevOps OS | jwl247 | GPL v3

Replaces Tailscale and WireGuard (JW, 2026-10-05). Nebula: no central server —
lighthouses only help machines find each other, then traffic goes direct
(or through a relay). We run our own certificate authority; each machine's
certificate says who it is (IP + groups) and the firewall works by group.

    python sector3/mesh/phoenix_net.py tools              # unpack nebula from the clone pool
    python sector3/mesh/phoenix_net.py ca                 # create the CA (once; key stays in the vault)
    python sector3/mesh/phoenix_net.py sign pbmiii        # certificate for a host in hosts.json
    python sector3/mesh/phoenix_net.py config pbmiii      # print its config.yml
    python sector3/mesh/phoenix_net.py install-local pbmii        # this Windows PC (admin)
    python sector3/mesh/phoenix_net.py install-ssh pbmiii         # a Debian box we can SSH into (sudo by key)
    python sector3/mesh/phoenix_net.py status

Certs and keys are written to the vault (F:\\Phoenix\\Vault\\secrets\\nebula-*), so
the next `phoenix_vault.py push` carries them, encrypted, for boxes set up remotely.
The nebula programs come from the clone pool (import method), never the internet.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOSTS = HERE / "hosts.json"
VAULT = Path(os.environ.get("PHOENIX_VAULT_SECRETS", r"F:\Phoenix\Vault\secrets"))
TOOLS = Path(os.environ.get("PHOENIX_MESH_TOOLS", r"F:\Phoenix\mesh\bin"))
WIN_HOME = Path(r"C:\Program Files\Nebula")
WIN_CONF = Path(r"C:\ProgramData\Nebula")
CA_NAME = "Phoenix Mesh"
HEAL_EVERY = "5min"
HOST_CERT_LIFE = "8760h"      # 1 year — renewed by `heal` when < 30 days remain (NIST IA-5 key rotation)


HEAL_SH = r"""#!/usr/bin/env bash
# phoenix-mesh-heal — keeps Phoenix Mesh healthy; every repair goes to the journal
# (journalctl -t phoenix-mesh-heal). Installed by sector3/mesh/phoenix_net.py.
set -u
log() { logger -t phoenix-mesh-heal "$*"; echo "$*"; }
C=/etc/nebula; KG=$C/known-good
# 1. config drift -> restore the known-good version
if [ -f "$KG/config.yml" ] && ! cmp -s "$KG/config.yml" "$C/config.yml"; then
  cp "$KG/config.yml" "$C/config.yml"; log "config drift: restored known-good ($(cat $C/VERSION 2>/dev/null))"
  systemctl restart nebula
fi
# 2. service down -> restart
if ! systemctl is-active -q nebula; then
  systemctl restart nebula; sleep 3
  systemctl is-active -q nebula && log "nebula was down: restarted" || log "nebula down: restart FAILED"
fi
# 3. lighthouse unreachable 3 checks in a row -> restart (fresh handshakes)
LH=$(cat "$C/lighthouse_ip" 2>/dev/null)
F=/run/phoenix-mesh-heal.fail
if [ -n "$LH" ]; then
  if ping -c 3 -W 3 "$LH" >/dev/null 2>&1; then echo 0 > $F
  else n=$(( $(cat $F 2>/dev/null || echo 0) + 1 )); echo $n > $F
       [ $n -ge 3 ] && { systemctl restart nebula; log "lighthouse $LH unreachable 3 checks: restarted nebula"; echo 0 > $F; }
  fi
fi
# 4. certificate close to expiry -> say so loudly (renewal is signed on the home PC)
days=$(/usr/local/bin/nebula-cert print -json -path "$C/host.crt" 2>/dev/null | python3 -c '
import json,sys,datetime as d
j=json.load(sys.stdin); j=j[0] if isinstance(j,list) else j
t=(j.get("details") or j)["notAfter"]
print((d.datetime.fromisoformat(t.replace("Z","+00:00"))-d.datetime.now(d.timezone.utc)).days)' 2>/dev/null)
[ -n "$days" ] && [ "$days" -lt 30 ] && log "WARNING: host certificate expires in $days days - run phoenix_net.py renew on the home PC"
exit 0
"""

HEAL_SERVICE = """[Unit]
Description=Phoenix Mesh self-heal check

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/phoenix-mesh-heal
"""

HEAL_TIMER = f"""[Unit]
Description=Phoenix Mesh self-heal every {HEAL_EVERY}

[Timer]
OnBootSec=2min
OnUnitActiveSec={HEAL_EVERY}
Persistent=true

[Install]
WantedBy=timers.target
"""


def version_tag(config_text: str) -> str:
    """Which config this box runs: git commit of the tool + sha256 of the rendered config."""
    import hashlib
    try:
        sha = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, check=True).stdout.strip()
    except Exception:
        sha = "nogit"
    return f"git:{sha} config:{hashlib.sha256(config_text.encode()).hexdigest()[:12]}"


def load() -> dict:
    return json.loads(HOSTS.read_text(encoding="utf-8"))


def host(cfg: dict, name: str) -> dict:
    h = cfg["hosts"].get(name)
    if not h:
        raise SystemExit(f"{name} is not in {HOSTS.name}")
    return h


def pool_file(name: str) -> Path:
    pool = os.environ.get("CLONEPOOL_DIR")
    if not pool and os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            pool = winreg.QueryValueEx(k, "CLONEPOOL_DIR")[0]
    d = Path(pool) / "T1" / name.encode().hex()
    found = sorted(d.glob(f"v*_{name}"), key=lambda p: int(p.name.split("_", 1)[0][1:]))
    if not found:
        raise SystemExit(f"{name} is not in the clone pool — intake it first")
    return found[-1]


def nebula_cert() -> Path:
    exe = TOOLS / ("nebula-cert.exe" if os.name == "nt" else "nebula-cert")
    if not exe.exists():
        raise SystemExit("run `phoenix_net.py tools` first")
    return exe


# ---------------------------------------------------------------------------

def cmd_tools(_a) -> None:
    TOOLS.mkdir(parents=True, exist_ok=True)
    src = pool_file("nebula-windows-amd64.zip")
    with zipfile.ZipFile(src) as z:
        z.extractall(TOOLS)
    print(f"unpacked {src.name} -> {TOOLS}")


def cmd_ca(_a) -> None:
    crt, key = VAULT / "nebula-ca.crt", VAULT / "nebula-ca.key"
    if key.exists():
        print(f"CA already exists ({crt.name}) — not replaced")
        return
    subprocess.run([str(nebula_cert()), "ca", "-name", CA_NAME, "-duration", "87600h",
                    "-out-crt", str(crt), "-out-key", str(key)], check=True)
    print(f"CA created (10 years): {crt}  — key stays in the vault")


def cmd_sign(a) -> None:
    cfg = load()
    h = host(cfg, a.host)
    crt, key = VAULT / f"nebula-{a.host}.crt", VAULT / f"nebula-{a.host}.key"
    for p in (crt, key):
        if p.exists():
            p.unlink()                       # re-sign replaces (e.g. new groups)
    prefix = cfg["network"].split("/")[1]
    subprocess.run([str(nebula_cert()), "sign", "-name", a.host, "-ip", f"{h['ip']}/{prefix}",
                    "-groups", ",".join(h["groups"]), "-duration", HOST_CERT_LIFE,
                    "-ca-crt", str(VAULT / "nebula-ca.crt"), "-ca-key", str(VAULT / "nebula-ca.key"),
                    "-out-crt", str(crt), "-out-key", str(key)], check=True)
    print(f"signed {a.host}: {h['ip']} groups={','.join(h['groups'])}")


def render(cfg: dict, name: str, pki_dir: str, sep: str) -> str:
    h = host(cfg, name)
    lh_names = list(cfg["lighthouses"])
    is_lh = name in lh_names
    lh_ips = [cfg["hosts"][n]["ip"] for n in lh_names]
    shm = "\n".join(f'  "{cfg["hosts"][n]["ip"]}": [{", ".join(json.dumps(x) for x in addrs)}]'
                    for n, addrs in cfg["lighthouses"].items())
    linux = h["os"] == "linux"
    if "servers" in h["groups"]:
        inbound = """    - port: any
      proto: any
      group: jerry
    - port: any
      proto: any
      group: servers"""
    elif linux:
        inbound = """    - port: 22
      proto: tcp
      group: jerry"""
    else:
        inbound = """    - port: 3389
      proto: tcp
      group: jerry"""
    return f"""# Phoenix Mesh — {name} ({h['ip']}) — generated by sector3/mesh/phoenix_net.py; edit hosts.json, not this
pki:
  ca: {pki_dir}{sep}ca.crt
  cert: {pki_dir}{sep}host.crt
  key: {pki_dir}{sep}host.key

static_host_map:
{shm}

lighthouse:
  am_lighthouse: {str(is_lh).lower()}
  interval: 60
  hosts: {json.dumps([] if is_lh else lh_ips)}

listen:
  host: "[::]"
  port: {cfg['port'] if (is_lh or linux) else 0}

punchy:
  punch: true
  respond: true

relay:
  am_relay: {str(is_lh or bool(h.get("relay"))).lower()}
  use_relays: true
  relays: {json.dumps([ip for ip in h.get("relays", lh_ips) if ip != h["ip"]])}

tun:
  dev: {"nebula1" if linux else "PhoenixMesh"}
  mtu: 1300

logging:
  level: info
  format: text

firewall:
  outbound_action: drop
  inbound_action: drop
  conntrack:
    tcp_timeout: 12m
    udp_timeout: 3m
    default_timeout: 10m
  outbound:
    - port: any
      proto: any
      host: any
  inbound:
    - port: any
      proto: icmp
      host: any
{inbound}
"""


def cmd_config(a) -> None:
    cfg = load()
    h = host(cfg, a.host)
    print(render(cfg, a.host, "/etc/nebula" if h["os"] == "linux" else str(WIN_CONF),
                 "/" if h["os"] == "linux" else "\\"))


def _pki(name: str) -> dict[str, bytes]:
    files = {"ca.crt": VAULT / "nebula-ca.crt", "host.crt": VAULT / f"nebula-{name}.crt",
             "host.key": VAULT / f"nebula-{name}.key"}
    missing = [str(p) for p in files.values() if not p.exists()]
    if missing:
        raise SystemExit(f"missing {', '.join(missing)} — run ca/sign first")
    return {k: v.read_bytes() for k, v in files.items()}


def cmd_install_local(a) -> None:
    cfg = load()
    h = host(cfg, a.host)
    if os.name != "nt" or h["os"] != "windows":
        raise SystemExit("install-local is for this Windows PC")
    exe = WIN_HOME / "nebula.exe"
    exists = "SERVICE_NAME" in subprocess.run(["sc.exe", "query", "nebula"], capture_output=True, text=True).stdout
    if exists:
        _stop_windows_service()      # never delete the service: stop, swap files, start (no "marked for deletion" race)
    WIN_HOME.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pool_file("nebula-windows-amd64.zip")) as z:
        z.extractall(WIN_HOME)
    WIN_CONF.mkdir(parents=True, exist_ok=True)
    for n, data in _pki(a.host).items():
        (WIN_CONF / n).write_bytes(data)
    conf = render(cfg, a.host, str(WIN_CONF), "\\")
    (WIN_CONF / "config.yml").write_text(conf, encoding="utf-8")
    (WIN_CONF / "known-good").mkdir(exist_ok=True)
    (WIN_CONF / "known-good" / "config.yml").write_text(conf, encoding="utf-8")
    (WIN_CONF / "VERSION").write_text(version_tag(conf) + "\n", encoding="utf-8")
    lh = "" if a.host in cfg["lighthouses"] else cfg["hosts"][next(iter(cfg["lighthouses"]))]["ip"]
    (WIN_CONF / "lighthouse_ip").write_text(lh, encoding="utf-8")
    # only Administrators and SYSTEM may read the key
    subprocess.run(["icacls", str(WIN_CONF), "/inheritance:r", "/grant:r", "Administrators:(OI)(CI)F",
                    "SYSTEM:(OI)(CI)F"], check=True, capture_output=True)
    subprocess.run([str(exe), "-test", "-config", str(WIN_CONF / "config.yml")], check=True)
    if not exists:
        subprocess.run([str(exe), "-service", "install", "-config", str(WIN_CONF / "config.yml")], check=True)
    # restart automatically if it ever stops (5 s, 10 s, 30 s; counter resets daily)
    subprocess.run(["sc.exe", "failure", "nebula", "reset=", "86400",
                    "actions=", "restart/5000/restart/10000/restart/30000"], check=True, capture_output=True)
    _start_windows_service()
    # self-heal check every 5 minutes, as SYSTEM
    task = f'"{sys.executable}" "{Path(__file__).resolve()}" heal-local'
    subprocess.run(["schtasks", "/Create", "/F", "/TN", "Phoenix Mesh Heal", "/SC", "MINUTE", "/MO", "5",
                    "/RU", "SYSTEM", "/RL", "HIGHEST", "/TR", task], check=True, capture_output=True)
    print(f"{a.host}: nebula running as a Windows service (auto-restart + 5-min heal task), "
          f"mesh address {h['ip']}  [{(WIN_CONF / 'VERSION').read_text().strip()}]")


def _stop_windows_service(timeout: int = 30) -> None:
    import time
    subprocess.run(["sc.exe", "stop", "nebula"], capture_output=True)
    for _ in range(timeout):
        q = subprocess.run(["sc.exe", "query", "nebula"], capture_output=True, text=True).stdout
        if "STOPPED" in q or "does not exist" in q or "1060" in q:
            time.sleep(1)                             # let the exe release its file handles
            return
        time.sleep(1)
    raise SystemExit("nebula service would not stop")


def _start_windows_service(tries: int = 5) -> None:
    """First start on a fresh PC installs the Wintun driver and can fail once - retry."""
    import time
    for _ in range(tries):
        subprocess.run(["sc.exe", "start", "nebula"], capture_output=True)
        time.sleep(4)
        if "RUNNING" in subprocess.run(["sc.exe", "query", "nebula"], capture_output=True, text=True).stdout:
            return
    raise SystemExit("nebula service would not start")


def _heal_log(msg: str) -> None:
    """Windows Application log, source 'Phoenix Mesh' - the audit trail of every repair."""
    print(msg)
    subprocess.run(["eventcreate", "/L", "APPLICATION", "/T", "WARNING", "/SO", "Phoenix Mesh",
                    "/ID", "100", "/D", msg[:900]], capture_output=True)


def cmd_heal_local(_a) -> None:
    import time
    conf, good = WIN_CONF / "config.yml", WIN_CONF / "known-good" / "config.yml"
    if good.exists() and (not conf.exists() or conf.read_bytes() != good.read_bytes()):
        conf.write_bytes(good.read_bytes())
        _heal_log(f"config drift: restored known-good ({(WIN_CONF / 'VERSION').read_text().strip()})")
        subprocess.run(["sc.exe", "stop", "nebula"], capture_output=True)
        time.sleep(3)
    if "RUNNING" not in subprocess.run(["sc.exe", "query", "nebula"], capture_output=True, text=True).stdout:
        try:
            _start_windows_service()
            _heal_log("nebula was down: restarted")
        except SystemExit:
            _heal_log("nebula down: restart FAILED")
    lhf = WIN_CONF / "lighthouse_ip"
    lh = lhf.read_text().strip() if lhf.exists() else ""
    if lh:
        fail = WIN_CONF / "heal.fail"
        ok = subprocess.run(["ping", "-n", "3", "-w", "3000", lh], capture_output=True).returncode == 0
        n = 0 if ok else (int(fail.read_text() or 0) if fail.exists() else 0) + 1
        if n >= 3:
            subprocess.run(["sc.exe", "stop", "nebula"], capture_output=True)
            time.sleep(3)
            _start_windows_service()
            _heal_log(f"lighthouse {lh} unreachable 3 checks: restarted nebula")
            n = 0
        fail.write_text(str(n))


def cert_days_left(crt: Path) -> int:
    import datetime as d
    out = subprocess.run([str(nebula_cert()), "print", "-json", "-path", str(crt)],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    j = j[0] if isinstance(j, list) else j
    t = (j.get("details") or j)["notAfter"]
    return (d.datetime.fromisoformat(t.replace("Z", "+00:00")) - d.datetime.now(d.timezone.utc)).days


def cmd_renew(a) -> None:
    """On the home PC (holds the CA): re-sign certs with < 30 days left and push them out."""
    cfg = load()
    for name, h in cfg["hosts"].items():
        crt = VAULT / f"nebula-{name}.crt"
        if not crt.exists():
            continue
        days = cert_days_left(crt)
        if days >= 30 and not a.force:
            print(f"  {name}: {days} days left - fine")
            continue
        cmd_sign(argparse.Namespace(host=name))
        if h["os"] == "windows" and os.name == "nt":
            cmd_install_local(argparse.Namespace(host=name))
        elif "ssh" in h:
            cmd_install_ssh(argparse.Namespace(host=name))
        else:
            print(f"  {name}: renewed in the vault - push with phoenix_vault.py, install on the box")


def _ssh(h: dict) -> list[str]:
    key = Path.home() / ".ssh" / h["ssh_key"]
    return ["ssh", "-i", str(key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", h["ssh"]]


def _scp(h: dict, src: Path, dst: str) -> None:
    key = Path.home() / ".ssh" / h["ssh_key"]
    user, addr = h["ssh"].split("@", 1)
    subprocess.run(["scp", "-i", str(key), "-o", "BatchMode=yes", str(src), f"{user}@[{addr}]:{dst}"], check=True)


def cmd_install_ssh(a) -> None:
    cfg = load()
    h = host(cfg, a.host)
    if h["os"] != "linux" or "ssh" not in h:
        raise SystemExit(f"{a.host}: needs os=linux and an ssh target in hosts.json")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        shutil.copy(pool_file("nebula-linux-amd64.tar.gz"), td / "nebula.tar.gz")
        for n, data in _pki(a.host).items():
            (td / n).write_bytes(data)
        conf = render(cfg, a.host, "/etc/nebula", "/")
        lh = "" if a.host in cfg["lighthouses"] else cfg["hosts"][next(iter(cfg["lighthouses"]))]["ip"]
        for name, text in {"config.yml": conf, "VERSION": version_tag(conf) + "\n",
                           "lighthouse_ip": lh + ("\n" if lh else ""), "phoenix-mesh-heal": HEAL_SH,
                           "phoenix-mesh-heal.service": HEAL_SERVICE,
                           "phoenix-mesh-heal.timer": HEAL_TIMER}.items():
            (td / name).write_text(text, encoding="utf-8", newline="\n")
        (td / "nebula.service").write_text("""[Unit]
Description=Phoenix Mesh (Nebula)
Wants=network-online.target
After=network-online.target

[Service]
ExecStartPre=/usr/local/bin/nebula -test -config /etc/nebula/config.yml
ExecStart=/usr/local/bin/nebula -config /etc/nebula/config.yml
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
""", encoding="utf-8", newline="\n")
        subprocess.run(_ssh(h) + ["mkdir -p ~/phoenix-mesh-stage && rm -f ~/phoenix-mesh-stage/*"], check=True)
        for f in td.iterdir():
            _scp(h, f, "phoenix-mesh-stage/")
    script = """set -e
cd ~/phoenix-mesh-stage
sudo tar -xzf nebula.tar.gz -C /usr/local/bin nebula nebula-cert
sudo chmod 755 /usr/local/bin/nebula /usr/local/bin/nebula-cert
sudo install -d -m 700 /etc/nebula
sudo install -m 644 ca.crt host.crt config.yml /etc/nebula/
sudo install -m 600 host.key /etc/nebula/
sudo install -m 644 nebula.service /etc/systemd/system/nebula.service
sudo install -m 644 VERSION lighthouse_ip /etc/nebula/
sudo install -d -m 700 /etc/nebula/known-good
sudo install -m 644 config.yml /etc/nebula/known-good/config.yml
sudo install -m 755 phoenix-mesh-heal /usr/local/sbin/phoenix-mesh-heal
sudo install -m 644 phoenix-mesh-heal.service phoenix-mesh-heal.timer /etc/systemd/system/
sudo /usr/local/bin/nebula -test -config /etc/nebula/config.yml
sudo systemctl daemon-reload
sudo systemctl enable nebula >/dev/null 2>&1
sudo systemctl enable --now phoenix-mesh-heal.timer >/dev/null 2>&1
__RESTART__
echo "heal timer: $(systemctl is-active phoenix-mesh-heal.timer)"
echo "version: $(sudo cat /etc/nebula/VERSION)"
cd ~ && rm -rf ~/phoenix-mesh-stage
"""
    over_mesh = h["ssh"].split("@", 1)[1].startswith("10.42.")
    if over_mesh:
        script = script.replace("__RESTART__\n", "sudo systemd-run --quiet --on-active=3 --unit=phoenix-nebula-restart-$RANDOM "
                                "systemctl restart nebula\necho restart-scheduled\n")
    else:
        script = script.replace("__RESTART__\n", "sudo systemctl restart nebula\nsleep 2\nsystemctl is-active nebula\n"
                                "ip -br addr show nebula1 | awk '{print $1, $3}'\n")
    # Send bytes with LF line endings only. Text mode on Windows would send CRLF,
    # and every remote command fails (a stray CR on each line).
    r = subprocess.run(_ssh(h) + ["bash -s"], input=script.encode(), capture_output=True)
    out = r.stdout.decode(errors="replace").strip()
    print(out)
    if over_mesh and r.returncode == 0 and "restart-scheduled" in out:
        import time
        time.sleep(12)                                       # restart happens, mesh re-handshakes
        v = subprocess.run(_ssh(h) + ["systemctl is-active nebula; ip -br addr show nebula1 | awk '{print $1, $3}'"],
                           capture_output=True)
        out = v.stdout.decode(errors="replace").strip()
        print(out)
    if r.returncode or "active" not in out.splitlines() or "nebula1" not in out:
        print(r.stderr.decode(errors="replace").strip())
        raise SystemExit(f"{a.host}: install FAILED — nebula is not running")
    print(f"{a.host}: nebula running as a systemd service, mesh address {h['ip']}")


def cmd_status(_a) -> None:
    cfg = load()
    for name, h in cfg["hosts"].items():
        flag = "-n" if os.name == "nt" else "-c"
        r = subprocess.run(["ping", flag, "1", "-w", "1500" if os.name == "nt" else "2", h["ip"]],
                           capture_output=True, text=True)
        ok = r.returncode == 0 and ("TTL=" in r.stdout or "ttl=" in r.stdout)
        print(f"  {name:<8} {h['ip']:<11} {'UP' if ok else '--'}   {h.get('note', '')}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="phoenix_net.py", description="Phoenix Mesh (Nebula)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tools")
    sub.add_parser("ca")
    for c in ("sign", "config", "install-local", "install-ssh"):
        sub.add_parser(c).add_argument("host")
    sub.add_parser("status")
    sub.add_parser("heal-local")
    sub.add_parser("renew").add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    {"tools": cmd_tools, "ca": cmd_ca, "sign": cmd_sign, "config": cmd_config,
     "install-local": cmd_install_local, "install-ssh": cmd_install_ssh, "status": cmd_status,
     "heal-local": cmd_heal_local, "renew": cmd_renew}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
