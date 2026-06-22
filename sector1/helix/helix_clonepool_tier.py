"""
helix_clonepool_tier.py  (sideload edition)
Self-contained clonepool fault-in tier. Runs ALONGSIDE Helix,
own hot-cache, borrows nothing from HelixMemoryManager.
"""
import os, sqlite3, time, logging
from pathlib import Path
from collections import OrderedDict
from typing import Optional, Dict

log = logging.getLogger("helix.clonepool")
DEFAULT_CATALOG = Path.home() / ".catalog" / "catalog.db"


class ClonepoolTier:
    def __init__(self, catalog_db: Path = DEFAULT_CATALOG,
                 hot_max_bytes: int = 256 * 1024 * 1024):
        self.catalog_db = Path(catalog_db)
        self.hot_max = hot_max_bytes
        self.address_map: Dict[str, str] = {}
        self._hot: "OrderedDict[str, bytes]" = OrderedDict()
        self._hot_bytes = 0
        self.stats = {
            "hydrated_entries": 0, "faults": 0, "fault_bytes": 0,
            "fault_misses": 0, "hits": 0, "fault_time_total": 0.0,
            "hit_time_total": 0.0, "evictions": 0,
        }
        self._hydrate()

    def _hydrate(self) -> int:
        if not self.catalog_db.exists():
            log.warning("catalog db not found at %s", self.catalog_db)
            return 0
        con = sqlite3.connect(f"file:{self.catalog_db}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT hex_id, destination FROM custody "
                "WHERE destination IS NOT NULL ORDER BY rowid").fetchall()
        finally:
            con.close()
        for hex_id, dest in rows:
            self.address_map[hex_id] = dest
        self.stats["hydrated_entries"] = len(self.address_map)
        log.info("hydrated %d clonepool entries", len(self.address_map))
        return len(self.address_map)

    def add_entry(self, hex_id: str, destination: str) -> None:
        self.address_map[hex_id] = destination

    def _cache_hot(self, key: str, data: bytes) -> None:
        while self._hot_bytes + len(data) > self.hot_max and self._hot:
            ok, ov = self._hot.popitem(last=False)
            self._hot_bytes -= len(ov)
            self.stats["evictions"] += 1
        self._hot[key] = data
        self._hot_bytes += len(data)

    def _fault_in(self, key: str) -> Optional[bytes]:
        path = self.address_map.get(key)
        if path is None:
            return None
        p = Path(path)
        if not p.exists():
            log.error("fault failed: %s -> missing file %s", key, path)
            return None
        t0 = time.perf_counter()
        data = p.read_bytes()
        self._cache_hot(key, data)
        dt = time.perf_counter() - t0
        self.stats["faults"] += 1
        self.stats["fault_bytes"] += len(data)
        self.stats["fault_time_total"] += dt
        log.info("faulted %s (%d bytes) in %.3f ms", key, len(data), dt * 1000)
        return data

    def read(self, key: str) -> Optional[bytes]:
        t0 = time.perf_counter()
        if key in self._hot:
            self._hot.move_to_end(key)
            self.stats["hits"] += 1
            self.stats["hit_time_total"] += time.perf_counter() - t0
            return self._hot[key]
        if key in self.address_map:
            return self._fault_in(key)
        self.stats["fault_misses"] += 1
        return None

    def known(self, key: str) -> bool:
        return key in self._hot or key in self.address_map

    def report(self) -> Dict:
        s = self.stats
        return {**s, "map_size": len(self.address_map),
                "hot_entries": len(self._hot),
                "hot_mb": round(self._hot_bytes / (1024*1024), 2),
                "avg_fault_ms": round(s["fault_time_total"]/s["faults"]*1000, 3) if s["faults"] else 0.0,
                "avg_hit_ms": round(s["hit_time_total"]/s["hits"]*1000, 4) if s["hits"] else 0.0}

    def print_report(self) -> None:
        r = self.report()
        print("\n" + "="*60)
        print("  HELIX CLONEPOOL TIER (sideload)")
        print("="*60)
        print(f"  map:    {r['map_size']:,} entries")
        print(f"  hot:    {r['hot_entries']:,} entries / {r['hot_mb']} MB")
        print(f"  hits:   {r['hits']:,}  avg {r['avg_hit_ms']:.4f} ms")
        print(f"  faults: {r['faults']:,}  avg {r['avg_fault_ms']:.3f} ms")
        print(f"  misses: {r['fault_misses']:,}   evictions: {r['evictions']:,}")
        print("="*60 + "\n")


def _self_test() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    print("\n=== clonepool tier (sideload) self-test ===\n")
    tier = ClonepoolTier()
    if not tier.address_map:
        print("FAIL: empty map"); return 1
    print(f"hydrated {len(tier.address_map):,} entries\n")
    sample = None
    for hx, pth in tier.address_map.items():
        if Path(pth).exists():
            sample = (hx, pth); break
    if not sample:
        print("FAIL: no mapped file exists on this box"); return 1
    hx, pth = sample
    expected = Path(pth).read_bytes()
    print(f"asset: {hx}  ({len(expected)} bytes)\n")
    print("[1] cold read (fault)...")
    if tier.read(hx) != expected:
        print("  FAIL bytes mismatch"); return 1
    assert tier.stats["faults"] == 1
    print("  PASS\n")
    print("[2] warm read (hot hit)...")
    fb = tier.stats["faults"]
    if tier.read(hx) != expected or tier.stats["faults"] != fb:
        print("  FAIL"); return 1
    print("  PASS\n")
    print("[3] unknown key...")
    if tier.read("ffffffffffffffffffffffff_nope") is not None:
        print("  FAIL"); return 1
    print("  PASS\n")
    tier.print_report()
    print("ALL PASS - sideload tier live\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
