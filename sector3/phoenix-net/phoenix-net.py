#!/usr/bin/env python3
"""phoenix-net — admin tool for Phoenix Mesh. Runs on Jerry's PC.

UnitedSys — United Systems | jwl247 | GPL-3.0

  phoenix-net.py enroll NAME --ssh ALIAS [--hub]   join a Linux box over SSH
  phoenix-net.py enroll-local NAME [--hub]         join THIS Windows PC (run as Administrator)
  phoenix-net.py enroll-phone NAME --hub-name H    make a WireGuard config for a phone (QR-ready)
  phoenix-net.py list                              everyone in the family
  phoenix-net.py links [--since ISO]               link health (direct / fallback / down)
  phoenix-net.py revoke NAME                       drop a device from the family, now

Reads MESH_ADMIN + MESH_WORKER_URL from the vault file
(F:\\Phoenix\\Vault\\secrets\\phoenix-secrets.env, or PHOENIX_SECRETS). Secrets are
never printed and never put on a command line: tokens travel over SSH stdin.
Private keys are made ON the device and never leave it (the phone is the one
exception, see enroll-phone).
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MESHD = os.path.join(HERE, "meshd", "meshd.py")
UNIT = os.path.join(HERE, "meshd", "phoenix-meshd.service")
VAULT = os.environ.get("PHOENIX_SECRETS", r"F:\Phoenix\Vault\secrets\phoenix-secrets.env")
OWNER = "jw.leftwich1@gmail.com"


def vault():
    v = {}
    with open(VAULT, encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, val = line.partition("=")
                v[k.strip()] = val.strip().strip('"')
    for k in ("MESH_ADMIN", "MESH_WORKER_URL"):
        if not v.get(k):
            sys.exit(f"{k} missing from {VAULT}")
    return v


def admin(method, path, body=None):
    v = vault()
    req = urllib.request.Request(v["MESH_WORKER_URL"].rstrip("/") + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {v['MESH_ADMIN']}",
                                          "Content-Type": "application/json", "User-Agent": "phoenix-net/1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"switchboard: {e.code} {e.read().decode(errors='replace')[:200]}")


def ssh(alias, command, stdin=None):
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=10", alias, command], input=stdin,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"[{alias}] {command.split()[0]}...: {r.stderr.strip()[-400:]}")
    return r.stdout


def enroll_ssh(a):
    v = vault()
    print(f"[{a.ssh}] installing WireGuard tools + the agent")
    ssh(a.ssh, "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wireguard-tools >/dev/null "
               "&& sudo mkdir -p /opt/phoenix-mesh")
    for src, dst in ((MESHD, "/opt/phoenix-mesh/meshd.py"), (UNIT, "/etc/systemd/system/phoenix-meshd.service")):
        ssh(a.ssh, f"sudo tee {dst} >/dev/null", stdin=open(src, encoding="utf-8").read().replace("\r\n", "\n"))
    print(f"[{a.ssh}] making keys on the device")
    pub = ssh(a.ssh, f"sudo python3 /opt/phoenix-mesh/meshd.py init --name {a.name} --worker {v['MESH_WORKER_URL']}").strip().splitlines()[-1]
    print(f"[{a.ssh}] public key {pub[:10]}… -> switchboard")
    r = admin("POST", "/enroll", {"name": a.name, "pubkey": pub, "owner_email": OWNER, "kind": "agent", "hub": a.hub})
    ssh(a.ssh, "sudo python3 /opt/phoenix-mesh/meshd.py token -", stdin=r["token"] + "\n")
    print(f"[{a.ssh}] firewall: mesh port + mesh interface")
    ssh(a.ssh, "sudo nft list chain inet phoenix input >/dev/null 2>&1 && "
               "{ sudo nft list chain inet phoenix input | grep -q 'udp dport 51820' || "
               "sudo nft insert rule inet phoenix input udp dport 51820 accept; "
               "sudo nft list chain inet phoenix input | grep -q wg-phx || "
               "sudo nft insert rule inet phoenix input iifname wg-phx accept; } || true")
    ssh(a.ssh, "sudo systemctl daemon-reload && sudo systemctl enable --now phoenix-meshd >/dev/null 2>&1; sleep 4; "
               "sudo systemctl is-active phoenix-meshd")
    print(f"enrolled {a.name} = {r['mesh_ip']} ({a.name}.phx)")


def enroll_local(a):
    v = vault()
    py = sys.executable
    out = subprocess.run([py, MESHD, "init", "--name", a.name, "--worker", v["MESH_WORKER_URL"]],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(out.stderr.strip() or "init failed (run as Administrator, WireGuard for Windows installed?)")
    pub = out.stdout.strip().splitlines()[-1]
    r = admin("POST", "/enroll", {"name": a.name, "pubkey": pub, "owner_email": OWNER, "kind": "agent", "hub": a.hub})
    t = subprocess.run([py, MESHD, "token", "-"], input=r["token"] + "\n", capture_output=True, text=True)
    if t.returncode != 0:
        sys.exit(t.stderr.strip())
    print(f"enrolled {a.name} = {r['mesh_ip']} ({a.name}.phx); now start the agent service")


def enroll_phone(a):
    """A phone can't run the agent, so its keypair is made here and the
    config shown ONCE for the WireGuard app to scan. It links to the hub PC."""
    priv = subprocess.run(["wg", "genkey"], capture_output=True, text=True).stdout.strip()
    pub = subprocess.run(["wg", "pubkey"], input=priv, capture_output=True, text=True).stdout.strip()
    if not priv or not pub:
        sys.exit("needs `wg` (WireGuard for Windows) on this PC")
    r = admin("POST", "/enroll", {"name": a.name, "pubkey": pub, "owner_email": OWNER, "kind": "static"})
    hub = next((d for d in admin("GET", "/devices")["devices"] if d["name"] == a.hub_name and not d.get("revoked_at")), None)
    if not hub:
        sys.exit(f"hub '{a.hub_name}' not enrolled yet")
    ep = next((e for e in hub["endpoints"] if e["family"] == 6), None) or next((e for e in hub["endpoints"]), None)
    endpoint = (f"[{ep['addr']}]:{ep['port']}" if ep and ep["family"] == 6 else f"{ep['addr']}:{ep['port']}") if ep else ""
    conf = (f"[Interface]\nPrivateKey = {priv}\nAddress = {r['mesh_ip']}/32\n\n"
            f"[Peer]\nPublicKey = {hub['pubkey']}\nAllowedIPs = 10.47.0.0/24\n"
            + (f"Endpoint = {endpoint}\n" if endpoint else "") + "PersistentKeepalive = 25\n")
    out = os.path.join(os.path.expanduser("~"), f"{a.name}-phoenix-mesh.conf")
    with open(out, "w", encoding="utf-8") as f:
        f.write(conf)
    print(f"enrolled {a.name} = {r['mesh_ip']}. Config written to {out}: import it in the WireGuard app, then DELETE the file.")


def cmd_list(a):
    for d in admin("GET", "/devices")["devices"]:
        state = "REVOKED" if d.get("revoked_at") else ("seen " + (d.get("last_seen") or "never"))
        eps = ", ".join(f"{e['addr']}" for e in d["endpoints"]) or "-"
        print(f"{d['name'] + '.phx':<18} {d['mesh_ip']:<12} {d['kind']:<7}{' hub' if d['hub'] else '    '}  {state:<28} {eps}")


def cmd_links(a):
    rows = admin("GET", f"/links?since={a.since}")["links"]
    latest = {}
    for r in rows:                              # newest first: keep the latest per pair
        latest.setdefault((r["from_device"], r["to_device"]), r)
    for (f, t), r in sorted(latest.items()):
        print(f"{f:>10} -> {t:<10} {r['path']:<9} handshake={r['handshake_age']}s rtt={r['rtt_ms']}ms "
              f"in={r['rx_bytes']} out={r['tx_bytes']} via={r['endpoint']}  @{r['at']}")


def cmd_revoke(a):
    print(admin("POST", "/revoke", {"name": a.name}))


def main():
    ap = argparse.ArgumentParser(prog="phoenix-net")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("enroll"); p.add_argument("name"); p.add_argument("--ssh", required=True)
    p.add_argument("--hub", action="store_true"); p.set_defaults(fn=enroll_ssh)
    p = sp.add_parser("enroll-local"); p.add_argument("name"); p.add_argument("--hub", action="store_true"); p.set_defaults(fn=enroll_local)
    p = sp.add_parser("enroll-phone"); p.add_argument("name"); p.add_argument("--hub-name", required=True); p.set_defaults(fn=enroll_phone)
    sp.add_parser("list").set_defaults(fn=cmd_list)
    p = sp.add_parser("links"); p.add_argument("--since", default="1970-01-01"); p.set_defaults(fn=cmd_links)
    p = sp.add_parser("revoke"); p.add_argument("name"); p.set_defaults(fn=cmd_revoke)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
