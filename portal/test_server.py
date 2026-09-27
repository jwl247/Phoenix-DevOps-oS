"""Tests for the portal's summary logic and HTTP guard. Run: python portal/test_server.py"""
import datetime as dt
import http.client
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402

NOW = dt.datetime(2026, 9, 27, 3, 0, 0, tzinfo=dt.timezone.utc)
ran = fails = 0


def t(name, fn):
    global ran, fails
    ran += 1
    try:
        fn()
        print(f"  ok  {name}")
    except Exception as e:
        fails += 1
        print(f"FAIL  {name}\n      {e!r}")


def at(sec_ago):
    return (NOW - dt.timedelta(seconds=sec_ago)).strftime("%Y-%m-%d %H:%M:%S")


DEVICES = [
    {"name": "precision", "mesh_ip": "10.47.0.2", "hub": True, "kind": "agent", "last_seen": at(10),
     "endpoints": [{"addr": "192.168.1.106", "family": 4}, {"addr": "2605::1", "family": 6}]},
    {"name": "compaq", "mesh_ip": "10.47.0.3", "hub": False, "kind": "agent", "last_seen": at(400), "endpoints": []},
    {"name": "gone", "mesh_ip": "10.47.0.4", "hub": False, "kind": "static", "last_seen": None, "revoked_at": at(9)},
]
ROWS = [
    {"at": at(90), "from_device": "precision", "to_device": "compaq", "path": "direct", "rtt_ms": 1.0, "endpoint": "192.168.1.141:51820"},
    {"at": at(60), "from_device": "precision", "to_device": "compaq", "path": "down", "rtt_ms": None, "endpoint": None},
    {"at": at(30), "from_device": "precision", "to_device": "compaq", "path": "direct", "rtt_ms": 3.0, "endpoint": "192.168.1.141:51820"},
    {"at": at(30), "from_device": "precision", "to_device": "gone", "path": "down", "rtt_ms": None, "endpoint": None},
]


def machines_online_and_revoked():
    s = server.summarize(DEVICES, ROWS, NOW)
    by = {m["name"]: m for m in s["machines"]}
    assert set(by) == {"precision", "compaq"}, "revoked device left out"
    assert by["precision"]["online"] and not by["compaq"]["online"], by
    assert by["precision"]["lan"] == ["192.168.1.106"], "LAN = IPv4 only"


def link_shares_flips_and_rtt():
    link = server.summarize(DEVICES, ROWS, NOW)["links"]
    assert len(link) == 1, "links to a revoked device are dropped"
    l = link[0]
    assert l["path"] == "direct" and l["rtt_ms"] == 3.0, "latest report wins"
    assert l["share"] == {"direct": 67, "fallback": 0, "down": 33}, l["share"]
    assert l["flips"] == 2 and l["rtt_avg"] == 2.0 and l["rtt_max"] == 3.0, l
    assert not l["stale"]


def iso_or_sqlite_times():
    assert server.parse_at("2026-09-27 03:00:00") == NOW
    assert server.parse_at("2026-09-27T03:00:00Z") == NOW
    assert server.parse_at(None) is None


def http_guard_and_routes():
    httpd = server.http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]

    def get(path, host):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", path, headers={"Host": host})
        r = c.getresponse()
        return r.status, dict(r.getheaders()), r.read()

    assert get("/", "evil.example")[0] == 421, "foreign Host refused (DNS rebinding)"
    st, h, body = get("/", f"precision.phx:{port}")
    assert st == 200 and b"Phoenix Net" in body
    assert "default-src 'self'" in h["Content-Security-Policy"]
    assert get("/", "10.47.0.2")[0] == 200, "mesh address allowed"
    assert get("/../server.py", "localhost")[0] == 404, "no files outside the page"
    httpd.shutdown()


t("machines: online window, revoked left out, LAN = IPv4", machines_online_and_revoked)
t("links: latest state, shares, flips, rtt", link_shares_flips_and_rtt)
t("times: SQLite and ISO forms", iso_or_sqlite_times)
t("http: Host guard, CSP, only the page's own files", http_guard_and_routes)
print(f"\n{ran - fails} passing, {fails} failing")
sys.exit(1 if fails else 0)
