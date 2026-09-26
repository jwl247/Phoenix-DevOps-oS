"""test_meshd.py — the agent's decision logic (no WireGuard, no network needed).
Run: python test_meshd.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meshd  # noqa: E402

fails = 0
ran = 0


def t(name, fn):
    global fails, ran
    ran += 1
    try:
        fn()
        print(f"  ok  {name}")
    except Exception as e:
        fails += 1
        print(f"FAIL  {name}\n      {e!r}")


PEER = {"name": "compaq", "pubkey": "k", "mesh_ip": "10.47.0.2", "endpoints": [
    {"addr": "192.168.1.141", "port": 51820, "family": 4, "scope": "lan"},
    {"addr": "2605:59ca:531b:9008::1", "port": 51820, "family": 6, "scope": "public"}]}


def same_lan_first():
    assert meshd.pick_endpoint(PEER, ["192.168.1.106"], True) == "192.168.1.141:51820"


def ipv6_when_not_same_lan():
    assert meshd.pick_endpoint(PEER, ["192.168.137.142"], True) == "[2605:59ca:531b:9008::1]:51820"


def none_means_fallback():
    assert meshd.pick_endpoint(PEER, ["10.1.1.1"], False) is None


def hosts_block_is_managed_and_idempotent():
    with tempfile.TemporaryDirectory() as d:
        meshd.HOSTS = os.path.join(d, "hosts")
        with open(meshd.HOSTS, "w") as f:
            f.write("127.0.0.1 localhost\n192.168.1.1 router\n")
        names = {"compaq.phx": "10.47.0.2", "precision.phx": "10.47.0.1"}
        meshd.write_hosts(names, [PEER], [{"to": "compaq", "path": "direct"}])
        once = open(meshd.HOSTS).read()
        meshd.write_hosts(names, [PEER], [{"to": "compaq", "path": "direct"}])
        assert open(meshd.HOSTS).read() == once, "second write changed the file"
        assert "127.0.0.1 localhost" in once and "192.168.1.1 router" in once, "user lines lost"
        assert once.count(meshd.HOSTS_BEGIN) == 1
        assert "10.47.0.2\tcompaq.phx" in once


def hosts_uses_lan_address_when_direct_is_down():
    with tempfile.TemporaryDirectory() as d:
        meshd.HOSTS = os.path.join(d, "hosts")
        open(meshd.HOSTS, "w").close()
        meshd.write_hosts({"compaq.phx": "10.47.0.2"}, [PEER], [{"to": "compaq", "path": "fallback"}])
        assert "192.168.1.141\tcompaq.phx" in open(meshd.HOSTS).read()


def phones_ride_through_the_hub():
    with tempfile.TemporaryDirectory() as d:
        meshd.KEY_FILE = os.path.join(d, "private.key")
        meshd.WG_SYNC_CONF = os.path.join(d, "s.conf")
        meshd.WG_FULL_CONF = os.path.join(d, "f.conf")
        open(meshd.KEY_FILE, "w").write("PRIVATEKEY\n")
        hub = {"name": "precision", "pubkey": "HUB", "mesh_ip": "10.47.0.1", "hub": True, "kind": "agent", "endpoints": []}
        phone = {"name": "phone", "pubkey": "PHONE", "mesh_ip": "10.47.0.4", "hub": False, "kind": "static", "endpoints": []}
        # a normal agent: no direct phone entry; the phone's /32 rides on the hub
        meshd.write_configs({"port": 51820}, {"mesh_ip": "10.47.0.2", "hub": False}, [hub, PEER | {"kind": "agent"}, phone], [], False)
        s = open(meshd.WG_SYNC_CONF).read()
        assert "PublicKey = PHONE" not in s, "phone listed directly on a non-hub"
        assert "AllowedIPs = 10.47.0.1/32, 10.47.0.4/32" in s, s
        assert "PRIVATEKEY" in s and "Address" not in s, "sync conf must not carry Address"
        # the hub: phone is a direct peer
        meshd.write_configs({"port": 51820}, {"mesh_ip": "10.47.0.1", "hub": True}, [PEER | {"kind": "agent"}, phone], [], False)
        assert "PublicKey = PHONE" in open(meshd.WG_SYNC_CONF).read()
        assert "Address = 10.47.0.1/24" in open(meshd.WG_FULL_CONF).read()


t("phones ride through the hub", phones_ride_through_the_hub)
t("same LAN is preferred", same_lan_first)
t("public IPv6 when not on the same LAN", ipv6_when_not_same_lan)
t("no direct path -> None (Cloudflare fallback)", none_means_fallback)
t("hosts block: managed, idempotent, user lines kept", hosts_block_is_managed_and_idempotent)
t("hosts: LAN address when the direct link is down", hosts_uses_lan_address_when_direct_is_down)
print(f"\n{ran - fails} passing, {fails} failing")
sys.exit(1 if fails else 0)
