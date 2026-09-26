#!/usr/bin/env python3
"""phoenix-meshd — the Phoenix Mesh agent. One per machine (Linux or Windows).

UnitedSys — United Systems | jwl247 | GPL-3.0

Phoenix Mesh = our own ZeroTier-style network: WireGuard links run DIRECT
between Phoenix machines; the phoenix-mesh-worker (Cloudflare) is only the
switchboard. This agent:
  - makes the device's WireGuard keypair LOCALLY (the private key never leaves
    this machine; only the public key is ever sent anywhere),
  - tells the switchboard where this machine can be reached (LAN IPv4 +
    public IPv6, same listen port),
  - pulls the family list and writes the WireGuard config,
  - measures every link, ingress and egress (handshake age, rtt, rx/tx bytes,
    direct vs fallback), and reports it on each heartbeat,
  - keeps <name>.phx names in the hosts file.

Commands (root / Administrator):
  meshd.py init   --name NAME --worker URL [--port 51820]   make keys, print the public key
  meshd.py token  TOKEN                                       store the device token from enrollment
  meshd.py once                                               one heartbeat + apply + report
  meshd.py run    [--every 30]                                loop forever (the service)
  meshd.py status                                             print links

Standard library only. Needs `wg` (wireguard-tools / WireGuard for Windows).
"""
import argparse
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

IFACE = "wg-phx"
IS_WIN = platform.system() == "Windows"
CONF_DIR = (os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "PhoenixMesh")
            if IS_WIN else "/etc/phoenix-mesh")
DEVICE_FILE = os.path.join(CONF_DIR, "device.json")
KEY_FILE = os.path.join(CONF_DIR, "private.key")
WG_FULL_CONF = os.path.join(CONF_DIR, f"{IFACE}.conf")        # [Interface] + Address, for first bring-up
WG_SYNC_CONF = os.path.join(CONF_DIR, f"{IFACE}.sync.conf")   # wg-only fields, for `wg syncconf`
HOSTS = (os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), r"System32\drivers\etc\hosts")
         if IS_WIN else "/etc/hosts")
HOSTS_BEGIN, HOSTS_END = "# >>> phoenix-mesh (managed) >>>", "# <<< phoenix-mesh <<<"
DIRECT_MAX_AGE = 180      # a handshake newer than this = the direct link is up
KEEPALIVE = 25
# Relay through the hub: when two satellites can't link directly (found live
# 2026-09-26: the Compaq on the LAN and pbm3 behind the Precision's cable have
# no working direct path), each side routes that peer via the hub instead.
RELAY_FILE = os.path.join(CONF_DIR, "relay.json")
RELAY_AFTER = 2           # consecutive failed checks before relaying
RELAY_RETRY_S = 600       # then try direct again every 10 minutes


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def wg_bin():
    if IS_WIN:
        p = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "WireGuard", "wg.exe")
        return p if os.path.exists(p) else "wg.exe"
    return shutil.which("wg") or "/usr/bin/wg"


def run(args, input_text=None, check=True):
    r = subprocess.run(args, input=input_text, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])}: {r.stderr.strip() or r.returncode}")
    return r.stdout


def lock_down(path):
    """Owner-only access to secrets (private key, token)."""
    if IS_WIN:
        # SYSTEM + Administrators only, no inheritance
        subprocess.run(["icacls", path, "/inheritance:r", "/grant:r", "SYSTEM:F", "/grant:r", "Administrators:F"],
                       capture_output=True)
    else:
        os.chmod(path, 0o600)


def load_device():
    with open(DEVICE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_device(d):
    os.makedirs(CONF_DIR, exist_ok=True)
    with open(DEVICE_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    lock_down(DEVICE_FILE)


# ── discovery: where can this machine be reached? ───────────────────────────
def local_addresses():
    """(LAN IPv4 list, public IPv6 list) on real interfaces. Mesh / tunnel /
    loopback / link-local addresses are skipped."""
    v4, v6 = set(), set()
    if IS_WIN:
        out = run(["powershell", "-NoProfile", "-Command",
                   "Get-NetIPAddress | ? { $_.InterfaceAlias -notmatch 'wg-phx|Loopback|vEthernet|Cloudflare' } "
                   "| % { $_.IPAddress }"], check=False)
        addrs = out.split()
    else:
        out = run(["ip", "-o", "addr", "show"], check=False)
        addrs = [m.group(2) for m in re.finditer(r"^\d+:\s+(\S+)\s+inet6?\s+([0-9a-fA-F:.]+)/", out, re.M)
                 if not m.group(1).startswith(("lo", IFACE, "CloudflareWARP", "docker"))]
    for a in addrs:
        try:
            ip = ipaddress.ip_address(a.split("%")[0])
        except ValueError:
            continue
        # link-local 169.254.x (Windows gives these to idle adapters) is not a
        # real LAN address: found live 2026-09-26, it sent pbm3 to a dead hop.
        if ip.version == 4 and ip.is_private and not ip.is_link_local and not str(ip).startswith("10.47.0."):
            v4.add(str(ip))
        elif ip.version == 6 and ip.is_global:
            v6.add(str(ip))
    return sorted(v4), sorted(v6)


_V6_OK = None


def v6_works(host, timeout=3):
    """Does this machine's IPv6 actually reach the internet? Having a global
    IPv6 address is not proof: pbm3 gets one through the Precision's
    connection sharing, but IPv6 isn't routed (live 2026-09-26), so every
    call stalled on IPv6 before falling back, and peers were handed a dead
    address. Tested once per cycle against the switchboard itself."""
    global _V6_OK
    try:
        infos = socket.getaddrinfo(host, 443, socket.AF_INET6, socket.SOCK_STREAM)
        with socket.create_connection(infos[0][4][:2], timeout=timeout):
            _V6_OK = True
    except OSError:
        _V6_OK = False
    return _V6_OK


_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_first_getaddrinfo(*args, **kwargs):
    res = _orig_getaddrinfo(*args, **kwargs)
    if _V6_OK is False:
        v4 = [r for r in res if r[0] == socket.AF_INET]
        return v4 or res
    return res


socket.getaddrinfo = _ipv4_first_getaddrinfo


def my_endpoints(port, v6_ok=True):
    v4, v6 = local_addresses()
    eps = [{"addr": a, "port": port, "scope": "lan"} for a in v4]
    if v6_ok:
        eps += [{"addr": a, "port": port, "scope": "public"} for a in v6]
    return eps


def pick_endpoint(peer, my_v4, have_v6):
    """Same LAN first (fastest), then public IPv6. None = no direct path known:
    the link rides the Cloudflare fallback."""
    for e in peer.get("endpoints", []):
        if e.get("family") == 4 and e.get("scope") == "lan":
            peer_net = ipaddress.ip_network(e["addr"] + "/24", strict=False)
            if any(ipaddress.ip_address(m) in peer_net for m in my_v4):
                return f"{e['addr']}:{e['port']}"
    if have_v6:
        for e in peer.get("endpoints", []):
            if e.get("family") == 6:
                return f"[{e['addr']}]:{e['port']}"
    return None


# ── switchboard ─────────────────────────────────────────────────────────────
def api(dev, method, path, body=None):
    req = urllib.request.Request(dev["worker"].rstrip("/") + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {dev['token']}",
                                          "Content-Type": "application/json",
                                          "User-Agent": "phoenix-meshd/1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


# ── WireGuard ───────────────────────────────────────────────────────────────
def write_configs(dev, self_view, peers, my_v4, have_v6, relayed=frozenset()):
    priv = open(KEY_FILE, encoding="utf-8").read().strip()
    iface = [f"PrivateKey = {priv}", f"ListenPort = {dev['port']}"]
    # Static devices (phones) can't run the agent: they link only to the hub.
    # Everyone else reaches them THROUGH the hub, so their addresses ride on
    # the hub's AllowedIPs instead of a direct peer entry. The hub itself
    # (and only the hub) holds them as direct peers.
    i_am_hub = bool(self_view.get("hub"))
    hub = next((p for p in peers if p.get("hub")), None)
    via_hub = [p for p in peers if not i_am_hub and hub is not None and p is not hub
               and (p.get("kind") == "static" or p["name"] in relayed)]
    peer_blocks = []
    for p in peers:
        if any(p is v for v in via_hub):
            continue
        allowed = [f"{p['mesh_ip']}/32"]
        if hub is not None and p is hub and not i_am_hub:
            allowed += [f"{v['mesh_ip']}/32" for v in via_hub]
        lines = ["[Peer]", f"PublicKey = {p['pubkey']}", f"AllowedIPs = {', '.join(allowed)}"]
        ep = pick_endpoint(p, my_v4, have_v6)
        if ep:
            lines.append(f"Endpoint = {ep}")
        lines.append(f"PersistentKeepalive = {KEEPALIVE}")
        peer_blocks.append("\n".join(lines))
    sync = "[Interface]\n" + "\n".join(iface) + "\n\n" + "\n\n".join(peer_blocks) + "\n"
    full = "[Interface]\n" + "\n".join(iface + [f"Address = {self_view['mesh_ip']}/24"]) + "\n\n" + "\n\n".join(peer_blocks) + "\n"
    for path, text in ((WG_SYNC_CONF, sync), (WG_FULL_CONF, full)):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        lock_down(path)


def iface_up():
    r = subprocess.run([wg_bin(), "show", IFACE], capture_output=True, text=True)
    return r.returncode == 0


def apply_wireguard(self_view):
    if not iface_up():
        if IS_WIN:
            exe = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "WireGuard", "wireguard.exe")
            run([exe, "/installtunnelservice", WG_FULL_CONF])
            time.sleep(3)
        else:
            run(["ip", "link", "add", IFACE, "type", "wireguard"])
            run(["ip", "address", "add", f"{self_view['mesh_ip']}/24", "dev", IFACE])
            run([wg_bin(), "setconf", IFACE, WG_SYNC_CONF])
            run(["ip", "link", "set", IFACE, "up"])
            return
    run([wg_bin(), "syncconf", IFACE, WG_SYNC_CONF])


# ── health: every link, ingress and egress ─────────────────────────────────
def ping_ms(ip, attempts=3):
    """RTT of the first echo reply out of up to `attempts` single pings.
    One lost packet is not a dead link (live 2026-09-26: the first packet of
    a relayed link through the hub is sometimes dropped)."""
    for _ in range(attempts):
        rtt = _ping_once(ip)
        if rtt is not None:
            return rtt
    return None


def _ping_once(ip):
    args = (["ping", "-n", "1", "-w", "1500", ip] if IS_WIN else ["ping", "-c", "1", "-W", "2", ip])
    r = subprocess.run(args, capture_output=True, text=True)
    # A reply is a reply: ping exits non-zero when an ICMP redirect also
    # arrives (the hub relaying between satellites triggers those), even
    # though the echo reply came back. Found live 2026-09-26.
    m = re.search(r"time[=<]\s*([\d.]+)\s*ms", r.stdout)
    return float(m.group(1)) if m else None


def link_health(peers, my_v4=(), relayed=frozenset()):
    dump = subprocess.run([wg_bin(), "show", IFACE, "dump"], capture_output=True, text=True).stdout.splitlines()
    by_key = {}
    for line in dump[1:]:
        f = line.split("\t")
        if len(f) >= 7:
            by_key[f[0]] = {"endpoint": None if f[2] == "(none)" else f[2],
                            "handshake": int(f[4]), "rx": int(f[5]), "tx": int(f[6])}
    now = int(time.time())
    links = []
    for p in peers:
        w = by_key.get(p["pubkey"], {})
        if p["name"] in relayed:
            rtt = ping_ms(p["mesh_ip"])          # goes via the hub
            links.append({"to": p["name"], "path": "fallback" if rtt is not None else "down",
                          "handshake_age": None, "rtt_ms": rtt, "rx_bytes": None, "tx_bytes": None,
                          "endpoint": "relay:hub", "use_mesh": rtt is not None})
            continue
        age = (now - w["handshake"]) if w.get("handshake") else None
        rtt = ping_ms(p["mesh_ip"]) if age is not None and age < DIRECT_MAX_AGE else None
        if age is not None and age < DIRECT_MAX_AGE and rtt is not None:
            path = "direct"
        else:
            # direct link down: can we still reach the peer's LAN address (via LAN or the Cloudflare tunnel)?
            lan = lan_fallback(p, my_v4)
            rtt = ping_ms(lan) if lan else None
            path = "fallback" if rtt is not None else "down"
        links.append({"to": p["name"], "path": path, "handshake_age": age, "rtt_ms": rtt,
                      "rx_bytes": w.get("rx"), "tx_bytes": w.get("tx"), "endpoint": w.get("endpoint"),
                      "use_mesh": path == "direct"})
    return links


# ── Phoenix names ──────────────────────────────────────────────────────────
def lan_fallback(peer, my_v4):
    """The peer's IPv4 LAN address for when the direct mesh link is down:
    one on a network we share first (reachable straight over the LAN), else
    any (reachable via the Cloudflare tunnel's private routes)."""
    v4 = [e["addr"] for e in peer.get("endpoints", []) if e.get("family") == 4]
    for a in v4:
        net = ipaddress.ip_network(a + "/24", strict=False)
        if any(ipaddress.ip_address(m) in net for m in my_v4):
            return a
    return v4[0] if v4 else None


def write_hosts(names, peers, links, my_v4=()):
    """<name>.phx -> mesh IP while the direct link is up; the peer's LAN
    address when it isn't (that path works on the LAN and via the tunnel)."""
    lan = {p["name"]: lan_fallback(p, my_v4) for p in peers}
    use_mesh = {l["to"]: l.get("use_mesh", l["path"] == "direct") for l in links}
    lines = [HOSTS_BEGIN]
    for host, mesh_ip in sorted(names.items()):
        n = host[:-4]
        ip = mesh_ip if use_mesh.get(n, True) or not lan.get(n) else lan[n]
        lines.append(f"{ip}\t{host}")
    lines.append(HOSTS_END)
    try:
        cur = open(HOSTS, encoding="utf-8", errors="replace").read()
    except OSError:
        cur = ""
    cur = re.sub(re.escape(HOSTS_BEGIN) + r".*?" + re.escape(HOSTS_END) + r"\n?", "", cur, flags=re.S)
    new = cur.rstrip("\n") + "\n" + "\n".join(lines) + "\n"
    if new != cur:
        with open(HOSTS, "w", encoding="utf-8") as f:
            f.write(new)


# ── commands ────────────────────────────────────────────────────────────────
def cmd_init(a):
    os.makedirs(CONF_DIR, exist_ok=True)
    if os.path.exists(KEY_FILE):
        log("keys already exist; keeping them")
    else:
        priv = run([wg_bin(), "genkey"]).strip()
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            f.write(priv + "\n")
        lock_down(KEY_FILE)
    pub = run([wg_bin(), "pubkey"], input_text=open(KEY_FILE, encoding="utf-8").read()).strip()
    dev = {"name": a.name, "worker": a.worker, "port": a.port, "pubkey": pub, "token": None}
    if os.path.exists(DEVICE_FILE):
        dev["token"] = load_device().get("token")
    save_device(dev)
    print(pub)


def cmd_token(a):
    if a.token == "-":                      # from stdin: keeps the token out of the process list
        a.token = sys.stdin.readline()
    if not re.fullmatch(r"[0-9a-f]{64}", a.token.strip()):
        sys.exit("token must be 64 hex characters")
    dev = load_device()
    dev["token"] = a.token.strip()
    save_device(dev)
    log("token stored")


def load_relay():
    try:
        with open(RELAY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def update_relay(state, links, peers, i_am_hub, now=None):
    """Decide per peer: direct, or relayed via the hub. Pure (testable)."""
    now = int(now if now is not None else time.time())
    hub = next((p["name"] for p in peers if p.get("hub")), None)
    for l in links:
        n, st = l["to"], state.get(l["to"], {})
        if i_am_hub or hub is None or n == hub:
            state.pop(n, None)
            continue
        if st.get("relay_since"):
            if now - st["relay_since"] >= RELAY_RETRY_S:
                state[n] = {"down": 0, "retry": now}        # give direct another chance
            continue
        if l["path"] == "direct":
            state.pop(n, None)
        else:
            st["down"] = st.get("down", 0) + 1
            if st["down"] >= RELAY_AFTER:
                st = {"relay_since": now}
            state[n] = st
    return state


def cycle(dev):
    my_v4, my_v6 = local_addresses()
    host = urllib.parse.urlparse(dev["worker"]).hostname
    v6_ok = bool(my_v6) and v6_works(host)
    if not my_v6:
        global _V6_OK
        _V6_OK = False
    my_v6 = my_v6 if v6_ok else []
    body = {"endpoints": my_endpoints(dev["port"], v6_ok)}
    state = load_relay()
    relayed = frozenset(n for n, st in state.items() if st.get("relay_since"))
    if iface_up():
        try:
            prev = api(dev, "GET", "/peers")
            body["links"] = link_health(prev["peers"], my_v4, relayed)
            state = update_relay(state, body["links"], prev["peers"], bool(prev["self"].get("hub")))
            with open(RELAY_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f)
            relayed = frozenset(n for n, st in state.items() if st.get("relay_since"))
        except Exception as e:                         # health is best-effort; the heartbeat must still go
            log(f"health: {e}")
    r = api(dev, "POST", "/heartbeat", body)
    write_configs(dev, r["self"], r["peers"], my_v4, bool(my_v6), relayed)
    apply_wireguard(r["self"])
    write_hosts(r["names"], r["peers"], body.get("links", []), my_v4)
    summary = ", ".join(f"{l['to']}={l['path']}{'(relay)' if l['to'] in relayed else ''}"
                        for l in body.get("links", [])) or "first cycle"
    log(f"{dev['name']} {r['self']['mesh_ip']}: {len(r['peers'])} peers; {summary}")


def cmd_once(a):
    cycle(load_device())


def cmd_run(a):
    dev = load_device()
    if not dev.get("token"):
        sys.exit("not enrolled yet (no token)")
    while True:
        try:
            cycle(dev)
        except urllib.error.HTTPError as e:
            log(f"switchboard said {e.code}{' (revoked?)' if e.code == 401 else ''}")
        except Exception as e:
            log(f"cycle failed: {e}")
        time.sleep(a.every)


def cmd_status(a):
    dev = load_device()
    peers = api(dev, "GET", "/peers")["peers"]
    for l in link_health(peers, local_addresses()[0]):
        print(f"{l['to']:<12} {l['path']:<9} handshake={l['handshake_age']}s rtt={l['rtt_ms']}ms "
              f"rx={l['rx_bytes']} tx={l['tx_bytes']} via={l['endpoint']}")


def main():
    ap = argparse.ArgumentParser(prog="meshd", description="Phoenix Mesh agent")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init"); p.add_argument("--name", required=True); p.add_argument("--worker", required=True)
    p.add_argument("--port", type=int, default=51820); p.set_defaults(fn=cmd_init)
    p = sp.add_parser("token"); p.add_argument("token"); p.set_defaults(fn=cmd_token)
    sp.add_parser("once").set_defaults(fn=cmd_once)
    p = sp.add_parser("run"); p.add_argument("--every", type=int, default=30); p.set_defaults(fn=cmd_run)
    sp.add_parser("status").set_defaults(fn=cmd_status)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
