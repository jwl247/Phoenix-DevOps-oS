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


def relay_after_two_failures_then_retry():
    peers = [{"name": "precision", "hub": True}, {"name": "pbm3", "hub": False}]
    st = {}
    st = meshd.update_relay(st, [{"to": "pbm3", "path": "down"}, {"to": "precision", "path": "direct"}], peers, False, now=1000)
    assert "relay_since" not in st.get("pbm3", {}), "relayed after one failure"
    st = meshd.update_relay(st, [{"to": "pbm3", "path": "down"}], peers, False, now=1030)
    assert st["pbm3"]["relay_since"] == 1030, st
    assert "precision" not in st, "the hub is never relayed"
    st = meshd.update_relay(st, [{"to": "pbm3", "path": "fallback"}], peers, False, now=1300)
    assert st["pbm3"].get("relay_since") == 1030, "stays relayed before the retry window"
    st = meshd.update_relay(st, [{"to": "pbm3", "path": "fallback"}], peers, False, now=1030 + meshd.RELAY_RETRY_S)
    assert "relay_since" not in st["pbm3"], "direct gets retried after 10 minutes"
    assert meshd.update_relay({}, [{"to": "pbm3", "path": "down"}] * 3, peers, True, now=1) == {}, "the hub never relays"


def relay_retries_only_when_direct_is_possible():
    peers = [{"name": "precision", "hub": True}, {"name": "pbm3", "hub": False}]
    down = [{"to": "pbm3", "path": "down"}]
    none = {"pbm3": None}
    st = meshd.update_relay({}, down, peers, False, now=0, candidates=none)
    st = meshd.update_relay(st, down, peers, False, now=30, candidates=none)
    assert st["pbm3"]["relay_since"] == 30
    st = meshd.update_relay(st, down, peers, False, now=30 + 10 * meshd.RELAY_MAX_RETRY_S, candidates=none)
    assert st["pbm3"].get("relay_since") == 30, "no direct candidate: the relay is never cut"
    cand = {"pbm3": "192.168.1.5:51820"}
    st = meshd.update_relay(st, down, peers, False, now=100, candidates=cand)
    assert "relay_since" not in st["pbm3"] and st["pbm3"]["tries"] == 1, "a new candidate is tried at once"
    st = meshd.update_relay(st, down, peers, False, now=130, candidates=cand)
    st = meshd.update_relay(st, down, peers, False, now=160, candidates=cand)
    assert st["pbm3"]["relay_since"] == 160
    st = meshd.update_relay(st, down, peers, False, now=160 + meshd.RELAY_RETRY_S, candidates=cand)
    assert st["pbm3"].get("relay_since") == 160, "same candidate failed once: waits 20 min, not 10"
    st = meshd.update_relay(st, down, peers, False, now=160 + 2 * meshd.RELAY_RETRY_S, candidates=cand)
    assert "relay_since" not in st["pbm3"] and st["pbm3"]["tries"] == 2, "retried after the doubled wait"


def relayed_peer_rides_the_hub_in_config():
    with tempfile.TemporaryDirectory() as d:
        meshd.KEY_FILE = os.path.join(d, "private.key")
        meshd.WG_SYNC_CONF = os.path.join(d, "s.conf")
        meshd.WG_FULL_CONF = os.path.join(d, "f.conf")
        open(meshd.KEY_FILE, "w").write("PRIVATEKEY\n")
        hub = {"name": "precision", "pubkey": "HUB", "mesh_ip": "10.47.0.2", "hub": True, "kind": "agent", "endpoints": []}
        pbm3 = {"name": "pbm3", "pubkey": "PBM3", "mesh_ip": "10.47.0.1", "hub": False, "kind": "agent", "endpoints": []}
        meshd.write_configs({"port": 51820}, {"mesh_ip": "10.47.0.3", "hub": False}, [hub, pbm3], [], False, frozenset({"pbm3"}))
        s = open(meshd.WG_SYNC_CONF).read()
        assert "PublicKey = PBM3" not in s and "AllowedIPs = 10.47.0.2/32, 10.47.0.1/32" in s, s


def _stub_ip(addr_out, iface_exists):
    cmds = []
    def fake_run(args, input_text=None, check=True):
        cmds.append(" ".join(args))
        return addr_out if args[:3] == ["ip", "-o", "-4"] else ""
    meshd.run, meshd.iface_up = fake_run, (lambda: iface_exists)
    return cmds


def iface_gets_its_address_back():
    # half-built from an earlier crash: link exists, no address -> address added, link up
    cmds = _stub_ip("", True)
    meshd.ensure_linux_iface("10.47.0.3")
    assert "ip link add wg-phx type wireguard" not in cmds, cmds
    assert "ip address replace 10.47.0.3/24 dev wg-phx" in cmds and "ip link set wg-phx up" in cmds, cmds
    # healthy: nothing re-added
    cmds = _stub_ip("7: wg-phx    inet 10.47.0.3/24 scope global wg-phx", True)
    meshd.ensure_linux_iface("10.47.0.3")
    assert not any("address replace" in c for c in cmds), cmds
    # fresh: link created first
    cmds = _stub_ip("", False)
    meshd.ensure_linux_iface("10.47.0.3")
    assert cmds[0] == "ip link add wg-phx type wireguard", cmds


def restore_brings_mesh_up_without_the_switchboard():
    real_win = meshd.IS_WIN
    meshd.IS_WIN = False
    try:
        with tempfile.TemporaryDirectory() as d:
            meshd.WG_FULL_CONF, meshd.WG_SYNC_CONF = os.path.join(d, "f.conf"), os.path.join(d, "s.conf")
            cmds = _stub_ip("", False)
            assert meshd.restore_last_config() is False and cmds == []      # never enrolled: nothing to restore
            open(meshd.WG_FULL_CONF, "w").write("[Interface]\nListenPort = 51820\nAddress = 10.47.0.3/24\n")
            open(meshd.WG_SYNC_CONF, "w").write("[Interface]\nListenPort = 51820\n")
            assert meshd.saved_mesh_ip() == "10.47.0.3"
            assert meshd.restore_last_config() is True
            assert "ip address replace 10.47.0.3/24 dev wg-phx" in cmds and cmds[-1].endswith(f"syncconf wg-phx {meshd.WG_SYNC_CONF}"), cmds
    finally:
        meshd.IS_WIN = real_win


def hosts_written_whole_or_not_at_all():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "hosts")
        open(path, "w").write("127.0.0.1 localhost\n")
        meshd.write_file_safely(path, "127.0.0.1 localhost\n10.47.0.2\tprecision.phx\n")
        assert open(path).read().endswith("precision.phx\n") and os.listdir(d) == ["hosts"]


t("relay after two failures, retry direct after 10 min", relay_after_two_failures_then_retry)
t("relay retries only when a direct path is possible, with backoff", relay_retries_only_when_direct_is_possible)
t("a relayed peer rides the hub in the config", relayed_peer_rides_the_hub_in_config)
t("phones ride through the hub", phones_ride_through_the_hub)
t("same LAN is preferred", same_lan_first)
t("public IPv6 when not on the same LAN", ipv6_when_not_same_lan)
t("no direct path -> None (Cloudflare fallback)", none_means_fallback)
t("hosts block: managed, idempotent, user lines kept", hosts_block_is_managed_and_idempotent)
t("hosts: LAN address when the direct link is down", hosts_uses_lan_address_when_direct_is_down)
t("half-built interface gets its address back", iface_gets_its_address_back)
t("restore: mesh comes up from the last config, no switchboard", restore_brings_mesh_up_without_the_switchboard)
t("hosts file written whole or not at all", hosts_written_whole_or_not_at_all)
print(f"\n{ran - fails} passing, {fails} failing")
sys.exit(1 if fails else 0)
