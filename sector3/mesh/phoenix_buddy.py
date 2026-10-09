#!/usr/bin/env python3
"""phoenix_buddy.py — mesh-wide healing: boxes heal EACH OTHER, not only themselves.
Phoenix DevOps OS | jwl247 | GPL v3

Each box runs `run` every 5 min. For every buddy listed for it in hosts.json ("buddies"):
  1. ask the buddy's peer agent for `status` — over the mesh, then the home LAN if the mesh is down
  2. healthy  -> keep a copy of its signed mesh known-good in the version store (one dir per version)
  3. unhealthy-> if its mesh config / known-good is damaged, hand back the version it should run
                (the agent installs it only if the hash AND the Phoenix config signature check out),
                then ask it to `heal`, then check again
  4. no answer on any path -> Wake-on-LAN if it has a "mac" and we share its LAN; otherwise report
Logs only on a CHANGE of state (no 5-minute spam); a problem a heal did not clear is retried hourly.
Every action is logged: Linux journal (journalctl -t phoenix-buddy), Windows F:\\Phoenix\\mesh\\buddy.log.

  python phoenix_buddy.py keys                  # PBMII: config-signing key + one buddy key per box (vault)
  python phoenix_buddy.py install <host>        # PBMII: agent (+ buddy runner if it has buddies) on <host>
  python phoenix_buddy.py run --me <host>       # on a box (timer/scheduled task does this)
  python phoenix_buddy.py check --me <host>     # one pass, print what it sees, change nothing
"""
import argparse, hashlib, io, json, os, socket, subprocess, sys, tarfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent

if os.name == "nt":
    # The 5-min task runs on Jerry's desktop: no console window may flash, ours or a child's (ssh,
    # netsh, ...). Every subprocess this run starts gets CREATE_NO_WINDOW unless it asks otherwise.
    class _QuietPopen(subprocess.Popen):
        def __init__(self, *a, **k):
            k.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
            super().__init__(*a, **k)
    subprocess.Popen = _QuietPopen
VERSION = "buddy-1.0.0"
AGENT = "/usr/local/sbin/phoenix-peer-agent"
PEER_USER = "phoenix-peer"
ALLOW_FROM = "10.42.0.0/16,192.168.1.0/24"
KEEP_VERSIONS = 10
RETRY_SECS = 3600
IS_WIN = os.name == "nt"
STORE = Path(r"F:\Phoenix\mesh\peers") if IS_WIN else Path("/var/lib/phoenix-buddy")
LOGFILE = Path(r"F:\Phoenix\mesh\buddy.log")


# ---------------------------------------------------------------- shared
def hosts(path=None) -> dict:
    p = Path(path) if path else (HERE / "hosts.json")
    return json.loads(p.read_text(encoding="utf-8"))


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    if IS_WIN:
        LOGFILE.parent.mkdir(parents=True, exist_ok=True)
        with LOGFILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    else:
        subprocess.run(["logger", "-t", "phoenix-buddy", msg], check=False)


def key_for(me: str) -> Path:
    if IS_WIN:
        return Path.home() / ".ssh" / f"phoenix_buddy_{me}_ed25519"
    return Path("/opt/phoenix-buddy/buddy_key")


def addrs(peer: dict, me: dict) -> list:
    """Mesh address first; the home LAN as the fallback when the mesh itself is what broke."""
    out = [peer["ip"]]
    lan = peer.get("lan")
    if lan and me.get("lan_net") and lan.startswith(me["lan_net"]):
        out.append(lan)
    return out


def call(peer: dict, me_name: str, me: dict, verb: str, stdin: bytes = None, timeout=40):
    """(addr, CompletedProcess) for the first address that answers; (None, None) if none do."""
    STORE.mkdir(parents=True, exist_ok=True)
    for a in addrs(peer, me):
        cmd = ["ssh", "-i", str(key_for(me_name)), "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
               "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={STORE / 'known_hosts'}",
               f"{PEER_USER}@{a}", verb]
        try:
            r = subprocess.run(cmd, input=stdin, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        if r.returncode != 255:          # 255 = ssh itself could not connect; anything else = the agent answered
            return a, r
    return None, None


def wake(mac: str) -> None:
    pkt = bytes.fromhex("ff" * 6 + mac.replace(":", "").replace("-", "") * 16)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for port in (9, 7):
            s.sendto(pkt, ("255.255.255.255", port))


def store_version(peer_name: str, tar_bytes: bytes) -> str:
    """Keep the peer's signed known-good, one dir per config hash. Returns the hash."""
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as t:
        files = {m.name: t.extractfile(m).read() for m in t.getmembers() if m.isfile()}
    need = {"config.yml", "config.yml.sig", "VERSION"}
    if set(files) != need:
        raise ValueError(f"export from {peer_name} has {sorted(files)}")
    h = hashlib.sha256(files["config.yml"]).hexdigest()[:12]
    if f"config:{h}".encode() not in files["VERSION"]:
        raise ValueError(f"export from {peer_name}: VERSION does not match config {h}")
    d = STORE / peer_name / h
    if not d.exists():
        d.mkdir(parents=True)
        for n, b in files.items():
            (d / n).write_bytes(b)
        log(f"{peer_name}: stored mesh version {h} ({files['VERSION'].decode().strip()})")
    os.utime(d)
    for old in sorted((STORE / peer_name).iterdir(), key=lambda p: p.stat().st_mtime)[:-KEEP_VERSIONS]:
        if old.is_dir() and old.name != h:
            for f in old.iterdir():
                f.unlink()
            old.rmdir()
    return h


def stored_tar(peer_name: str, want: str):
    d = STORE / peer_name / want
    if not d.is_dir():
        vers = sorted((STORE / peer_name).glob("*/config.yml"), key=lambda p: p.stat().st_mtime) \
            if (STORE / peer_name).exists() else []
        if want or not vers:
            return None, None
        d = vers[-1].parent                      # VERSION unreadable on the box: newest version we hold
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for n in ("config.yml", "config.yml.sig", "VERSION"):
            t.add(d / n, arcname=n)
    return d.name, buf.getvalue()


# ---------------------------------------------------------------- run
def state_file(peer_name):
    return STORE / peer_name / "state.json"


def look(peer_name, peer, me_name, me):
    a, r = call(peer, me_name, me, "status")
    if r is None:
        return None, None
    try:
        return a, json.loads(r.stdout.decode())
    except ValueError:
        return a, {"healthy": False, "problems": [f"agent:bad-reply:{r.stderr.decode()[-120:]}"], "mesh": {}}


def one_peer(peer_name, cfg, me_name, act=True):
    peer, me = cfg["hosts"][peer_name], cfg["hosts"][me_name]
    sf = state_file(peer_name)
    sf.parent.mkdir(parents=True, exist_ok=True)
    prev = json.loads(sf.read_text()) if sf.exists() else {}
    a, st = look(peer_name, peer, me_name, me)

    if st is None:
        problems = ["unreachable"]
        if act and peer.get("mac") and peer.get("lan", "").startswith(me.get("lan_net", "-")):
            wake(peer["mac"])
            problems.append("wol-sent")
    else:
        problems = st.get("problems", [])
        # keep its mesh version whenever its MESH is sound — other drift (harden/shares) doesn't spoil it
        if act and not any(p.startswith("mesh:") for p in problems):
            _, r = call(peer, me_name, me, "export mesh")
            if r is not None and r.returncode == 0:
                try:
                    store_version(peer_name, r.stdout)
                except ValueError as e:
                    log(f"{peer_name}: version not stored: {e}")
        if act and not st.get("healthy"):
            sig = sorted(problems)
            if sig == prev.get("problems") and time.time() - prev.get("acted", 0) < RETRY_SECS:
                problems = sig                      # same problem, healed recently: wait, don't hammer
            else:
                mesh = st.get("mesh", {})
                if any(p.startswith("mesh:") and p != "mesh:down" for p in problems):
                    want = mesh.get("version", "").split("config:")[-1] if "config:" in mesh.get("version", "") else ""
                    h, tb = stored_tar(peer_name, want)
                    if tb:
                        _, r = call(peer, me_name, me, f"restore mesh {h}", stdin=tb)
                        log(f"{peer_name}: restore mesh {h} -> {(r.stdout or r.stderr).decode().strip() if r else 'no answer'}")
                        time.sleep(15)              # nebula restarts, handshakes again
                    else:
                        log(f"{peer_name}: mesh damaged and no stored version {want or '(any)'} to give back")
                _, r = call(peer, me_name, me, "heal", timeout=120)
                after = json.loads(r.stdout.decode()) if r is not None and r.returncode == 0 else None
                left = after.get("problems", []) if after else ["unreachable-after-heal"]
                log(f"{peer_name} via {a}: {', '.join(problems)} -> healed by {me_name}; "
                    + ("now healthy" if not left else "still: " + ", ".join(left)))
                problems = sorted(left)
                prev["acted"] = time.time()

    new = {"problems": sorted(problems), "via": a, "acted": prev.get("acted", 0), "seen": int(time.time())}
    if act:
        if new["problems"] != prev.get("problems"):
            log(f"{peer_name}: " + ("healthy" if not problems else ", ".join(problems)) + (f" (via {a})" if a else ""))
        sf.write_text(json.dumps(new))
    return a, st, problems


# ---------------------------------------------------------------- the kernel on THIS box (2026-10-09)
# The buddy runs as the person (not SYSTEM), so it is the one that may start their kernel: started as
# SYSTEM the kernel would get SYSTEM's home and lose its closet. 2026-10-08 the kernel ran DEGRADED a
# whole day (another program held Helix-I 7701-7704) and nothing healed or said it.
KERNEL_STATUS_PORT = 8765
HELIX_PORTS = (7701, 7702, 7703, 7704, 7805, 7806, 7807, 7808)
REPO = HERE.parents[1]
GENIE_HOME = Path(os.environ.get("PHOENIX_GENIE_HOME", Path.home() / ".phoenix" / "genie"))


def _listeners() -> dict:
    """port -> pid of whoever LISTENs on 127.0.0.1/0.0.0.0 (netstat: loopback-safe, no admin)."""
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    owners = {}
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 5 and f[3].upper() == "LISTENING" and ":" in f[1]:
            try:
                owners.setdefault(int(f[1].rsplit(":", 1)[1]), int(f[4]))
            except ValueError:
                pass
    return owners


def _proc_name(pid: int) -> str:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return out.split('","')[0].strip('"') if out.strip().startswith('"') else "?"


def kernel_look() -> list:
    """Problems with this box's kernel; [] = healthy."""
    own = _listeners()
    kpid = own.get(KERNEL_STATUS_PORT)
    if not kpid:
        return ["kernel:down"]
    bad = []
    for port in HELIX_PORTS:
        holder = own.get(port)
        if holder != kpid:
            bad.append(f"{port}:{'free' if not holder else f'{_proc_name(holder)}#{holder}'}")
    return [f"kernel:degraded:{','.join(bad)}"] if bad else []


def _genie(verb: str) -> str:
    g = REPO / "sector1" / "kernel" / "genie" / "genie.ps1"
    env = dict(os.environ, PHOENIX_GENIE_AUTOUP="0")
    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", f". '{g}'; genie {verb}"],
                       capture_output=True, text=True, env=env, timeout=180)
    return " ".join((r.stdout + r.stderr).split())[-200:]


def kernel_heal(act=True) -> list:
    sf = state_file("kernel-self")
    sf.parent.mkdir(parents=True, exist_ok=True)
    prev = json.loads(sf.read_text()) if sf.exists() else {}
    if (GENIE_HOME / "stopped-on-purpose").exists():   # a person said `lol stop`: down is the right state
        if act and prev.get("problems") != ["stopped-on-purpose"]:
            log("kernel (this box): stopped on purpose (lol stop) - left down until `lol start`")
            sf.write_text(json.dumps({"problems": ["stopped-on-purpose"], "acted": prev.get("acted", 0), "seen": int(time.time())}))
        return []
    problems = kernel_look()
    if act and problems:
        sig = sorted(problems)
        if not (sig == prev.get("problems") and time.time() - prev.get("acted", 0) < RETRY_SECS):
            p = problems[0]
            held = p.startswith("kernel:degraded:") and any(not x.endswith(":free") for x in p.split(":", 2)[2].split(","))
            if held:
                # another program holds Helix ports: never kill someone else's process; say who
                log(f"kernel (this box): {p} -> NOT healed: another program holds Helix ports; stop it, then the next pass restarts the kernel")
            else:
                said = _genie("restart" if p.startswith("kernel:degraded") else "up")
                left = kernel_look()
                log(f"kernel (this box): {p} -> {'restarted' if p.startswith('kernel:degraded') else 'started'} by the buddy; "
                    + ("now healthy" if not left else "still: " + ", ".join(left)) + f" [{said}]")
                problems = left
            prev["acted"] = time.time()
    new = {"problems": sorted(problems), "acted": prev.get("acted", 0), "seen": int(time.time())}
    if act:
        if new["problems"] != prev.get("problems") and not problems:
            log("kernel (this box): healthy")
        sf.write_text(json.dumps(new))
    return problems


def cmd_run(args, act=True):
    cfg = hosts(args.hosts)
    me = cfg["hosts"].get(args.me) or sys.exit(f"{args.me} not in hosts.json")
    if IS_WIN and (REPO / "sector1" / "kernel" / "genie" / "genie.ps1").exists():
        problems = kernel_heal(act=act)
        if not act:
            print(f"{'kernel':8} {'(this box)':17} " + ("healthy" if not problems else ", ".join(problems)))
    for p in me.get("buddies", []):
        a, st, problems = one_peer(p, cfg, args.me, act=act)
        if not act:
            print(f"{p:8} via {a or '-':14} " + ("healthy" if not problems else ", ".join(problems)))


# ---------------------------------------------------------------- PBMII-side setup
def cmd_keys(_a):
    import phoenix_net as pn
    sk = pn.SIGN_KEY
    if not sk.exists():
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "phoenix-config-sign", "-f", str(sk)], check=True)
        print(f"made config-signing key {sk.name} (vault)")
    for name, h in hosts()["hosts"].items():
        if not h.get("buddies"):
            continue
        k = pn.VAULT / f"phoenix-buddy-{name}_ed25519"
        if not k.exists():
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"phoenix-buddy-{name}", "-f", str(k)], check=True)
            print(f"made buddy key for {name} (vault)")
        if h["os"] == "windows":
            dst = key_for(name)
            dst.write_bytes(k.read_bytes()); Path(str(dst) + ".pub").write_bytes(Path(str(k) + ".pub").read_bytes())
            subprocess.run(["icacls", str(dst), "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:F"], capture_output=True)


def cmd_install(a):
    import phoenix_net as pn, tempfile, shutil
    cfg = hosts(); h = pn.host(cfg, a.host)
    if h["os"] == "windows":
        return install_windows(a.host, cfg)
    healers = [n for n, x in cfg["hosts"].items() if a.host in x.get("buddies", [])]
    lines = []
    for n in healers:
        pub = (pn.VAULT / f"phoenix-buddy-{n}_ed25519.pub").read_text().strip()
        lines.append(f'restrict,from="{ALLOW_FROM}",command="sudo -n {AGENT}" {pub}')
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        shutil.copy(HERE / "peer_agent.sh", td / "phoenix-peer-agent")
        (td / "authorized_keys").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        (td / "sudoers").write_text(
            f'Defaults:{PEER_USER} env_keep += "SSH_ORIGINAL_COMMAND SSH_CLIENT"\n'
            f"{PEER_USER} ALL=(root) NOPASSWD: {AGENT}\n", encoding="utf-8", newline="\n")
        buddy = bool(h.get("buddies"))
        if buddy:
            shutil.copy(HERE / "phoenix_buddy.py", td / "phoenix_buddy.py")
            shutil.copy(HERE / "hosts.json", td / "hosts.json")
            shutil.copy(pn.VAULT / f"phoenix-buddy-{a.host}_ed25519", td / "buddy_key")
            (td / "phoenix-buddy.service").write_text(
                "[Unit]\nDescription=Phoenix buddy heal (heal the other boxes)\nAfter=network-online.target nebula.service\n"
                f"[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /opt/phoenix-buddy/phoenix_buddy.py run --me {a.host} "
                "--hosts /opt/phoenix-buddy/hosts.json\n", encoding="utf-8", newline="\n")
            (td / "phoenix-buddy.timer").write_text(
                "[Unit]\nDescription=Phoenix buddy heal every 5 min\n[Timer]\nOnBootSec=3min\nOnUnitActiveSec=5min\n"
                "Persistent=true\n[Install]\nWantedBy=timers.target\n", encoding="utf-8", newline="\n")
        for f in td.iterdir():
            f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n"))
        subprocess.run(pn._ssh(h) + ["rm -rf ~/phoenix-buddy-stage && mkdir -p ~/phoenix-buddy-stage"], check=True)
        for f in td.iterdir():
            pn._scp(h, f, "phoenix-buddy-stage/")
    script = f"""set -e
cd ~/phoenix-buddy-stage
sudo install -m 755 -o root -g root phoenix-peer-agent {AGENT}
id {PEER_USER} >/dev/null 2>&1 || sudo useradd --system --create-home --shell /bin/sh {PEER_USER}
sudo install -d -m 700 -o {PEER_USER} -g {PEER_USER} /home/{PEER_USER}/.ssh
sudo install -m 600 -o {PEER_USER} -g {PEER_USER} authorized_keys /home/{PEER_USER}/.ssh/authorized_keys
sudo install -m 440 -o root -g root sudoers /etc/sudoers.d/91-phoenix-peer
sudo visudo -cf /etc/sudoers.d/91-phoenix-peer >/dev/null
if [ -f phoenix_buddy.py ]; then
  sudo install -d -m 700 /opt/phoenix-buddy /var/lib/phoenix-buddy
  sudo install -m 644 phoenix_buddy.py hosts.json /opt/phoenix-buddy/
  sudo install -m 600 buddy_key /opt/phoenix-buddy/buddy_key
  sudo install -m 644 phoenix-buddy.service phoenix-buddy.timer /etc/systemd/system/
  sudo systemctl daemon-reload && sudo systemctl enable --now phoenix-buddy.timer >/dev/null 2>&1
  echo "buddy timer: $(systemctl is-active phoenix-buddy.timer)"
fi
echo "agent: $(sudo {AGENT} version)  healers allowed: {len(lines)}"
cd ~ && rm -rf ~/phoenix-buddy-stage
"""
    r = subprocess.run(pn._ssh(h) + ["bash -s"], input=script.encode(), capture_output=True)
    print(r.stdout.decode().strip(), r.stderr.decode().strip())
    if r.returncode:
        raise SystemExit(f"{a.host}: buddy install FAILED")


def install_windows(name, cfg):
    py = sys.executable
    pyw = Path(py).with_name("pythonw.exe")      # windowless: python.exe flashed a console every 5 min
    if pyw.exists():
        py = str(pyw)
    task = "Phoenix Buddy Heal"
    ps = (f"$a=New-ScheduledTaskAction -Execute '{py}' -Argument '\"{HERE / 'phoenix_buddy.py'}\" run --me {name}' "
          f"-WorkingDirectory '{HERE}';"
          "$t=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5);"
          "$s=New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -MultipleInstances IgnoreNew;"
          f"Register-ScheduledTask -TaskName '{task}' -Action $a -Trigger $t -Settings $s -Force | Out-Null;"
          f"(Get-ScheduledTask -TaskName '{task}').State")
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    print(f"{name}: scheduled task '{task}': {r.stdout.strip()} {r.stderr.strip()}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keys")
    p = sub.add_parser("install"); p.add_argument("host")
    for n in ("run", "check"):
        p = sub.add_parser(n); p.add_argument("--me", required=True); p.add_argument("--hosts")
    a = ap.parse_args()
    if a.cmd == "keys": cmd_keys(a)
    elif a.cmd == "install": cmd_install(a)
    elif a.cmd == "run": cmd_run(a, act=True)
    else: cmd_run(a, act=False)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    main()
