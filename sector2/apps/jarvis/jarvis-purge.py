#!/usr/bin/env python3
"""jarvis-purge — forget Jarvis's stored prompts and answers after 30 days (JARVIS-S07).
Phoenix DevOps OS | jwl247 | GPL v3

Jerry, 2026-10-07: "yes, 30-day Jarvis purge" (no spies, semi-open book: nothing kept forever).
Runs daily from jarvis-purge.timer as the `jarvis` user. Deletes from traces.db every ask
older than DAYS (its row, its steps), rebuilds the search index (it only updates on insert, so
deleted text would otherwise stay findable), then VACUUMs so the bytes are really gone.
Kept on purpose: audit.db (security events) and telemetry.db (token counts, no text).

  jarvis-purge                    purge (default db, 30 days)
  jarvis-purge --db F --days N    test on a copy
"""
import argparse, sqlite3, sys, time

DB = "/var/lib/jarvis/.openjarvis/traces.db"


def purge(db: str, days: int) -> int:
    cutoff = time.time() - days * 86400
    con = sqlite3.connect(db, timeout=30)          # Jarvis may be writing: wait, don't fail
    try:
        con.execute("BEGIN IMMEDIATE")
        old = [r[0] for r in con.execute("SELECT trace_id FROM traces WHERE started_at < ?", (cutoff,))]
        if old:
            con.executemany("DELETE FROM trace_steps WHERE trace_id = ?", [(t,) for t in old])
            con.executemany("DELETE FROM traces WHERE trace_id = ?", [(t,) for t in old])
            con.execute("INSERT INTO traces_fts(traces_fts) VALUES('rebuild')")
        con.commit()
        if old:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con.execute("VACUUM")
        return len(old)
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(prog="jarvis-purge")
    ap.add_argument("--db", default=DB)
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    if a.days < 1:
        print("jarvis-purge: --days must be 1 or more", file=sys.stderr)
        return 2
    n = purge(a.db, a.days)
    print(f"jarvis-purge: {n} ask(s) older than {a.days} days forgotten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
