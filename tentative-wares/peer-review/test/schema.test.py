"""Forum schema rules, tested against SQLite (what D1 runs).

Every rule the schema claims is tried both ways: the legal move works and the
illegal one is refused by the database itself.
"""
import pathlib, sqlite3, sys

SCHEMA = pathlib.Path(__file__).resolve().parent.parent / "worker" / "schema.sql"
db = sqlite3.connect(":memory:")
db.execute("PRAGMA foreign_keys = ON")
db.executescript(SCHEMA.read_text(encoding="utf-8"))
db.executescript(SCHEMA.read_text(encoding="utf-8"))   # re-runnable (IF NOT EXISTS / OR IGNORE)

passed = failed = 0
def ok(label, cond):
    global passed, failed
    if cond: passed += 1
    else: failed += 1; print("FAIL", label)
def refused(label, sql, args=(), match=""):
    global passed, failed
    try:
        db.execute(sql, args)
    except sqlite3.DatabaseError as e:
        if match and match not in str(e): failed += 1; print("FAIL (wrong error)", label, e)
        else: passed += 1
        return
    failed += 1; print("FAIL (allowed)", label)
q = lambda sql, args=(): db.execute(sql, args).fetchone()
board = lambda slug: q("SELECT id FROM boards WHERE slug=?", (slug,))[0]

ok("4 boards seeded once", q("SELECT COUNT(*) FROM boards")[0] == 4)
for h in ("jw", "ann", "bob", "cat", "dan"):
    db.execute("INSERT INTO members (handle, display) VALUES (?, ?)", (h + "_x", h))
JW, ANN, BOB, CAT, DAN = 1, 2, 3, 4, 5
refused("bad handle", "INSERT INTO members (handle, display) VALUES ('a b!', 'x')")
refused("handle with a space later", "INSERT INTO members (handle, display) VALUES ('abc def', 'x')")

# ranks
refused("rank can't be set directly", "UPDATE members SET rank='owner' WHERE id=?", (ANN,), "rank_events")
db.execute("INSERT INTO rank_events (member_id, from_rank, to_rank, reason) VALUES (?, 'member', 'owner', 'bootstrap')", (JW,))
ok("owner bootstrap", q("SELECT rank FROM members WHERE id=?", (JW,))[0] == "owner")
refused("second ungranted owner", "INSERT INTO rank_events (member_id, from_rank, to_rank, reason) VALUES (?, 'member', 'owner', 'me too')", (ANN,), "grantor")
refused("ungranted moderator", "INSERT INTO rank_events (member_id, from_rank, to_rank, reason) VALUES (?, 'member', 'moderator', 'x')", (ANN,), "grantor")
refused("wrong from_rank", "INSERT INTO rank_events (member_id, from_rank, to_rank, reason, granted_by) VALUES (?, 'reviewer', 'moderator', 'x', ?)", (ANN, JW), "from_rank")
db.execute("INSERT INTO rank_events (member_id, from_rank, to_rank, reason, granted_by) VALUES (?, 'member', 'reviewer', 'known reviewer', ?)", (ANN, JW))
db.execute("INSERT INTO rank_events (member_id, from_rank, to_rank, reason, granted_by) VALUES (?, 'member', 'moderator', 'mod', ?)", (DAN, JW))
ok("owner grants reviewer and moderator", q("SELECT rank FROM members WHERE id=?", (ANN,))[0] == "reviewer" and q("SELECT rank FROM members WHERE id=?", (DAN,))[0] == "moderator")
refused("moderator can't make a moderator", "INSERT INTO rank_events (member_id, from_rank, to_rank, reason, granted_by) VALUES (?, 'member', 'moderator', 'x', ?)", (CAT, DAN), "grantor")
refused("nobody changes own rank", "INSERT INTO rank_events (member_id, from_rank, to_rank, reason, granted_by) VALUES (?, 'moderator', 'owner', 'x', ?)", (DAN, DAN), "grantor")
refused("member can't grant", "INSERT INTO rank_events (member_id, from_rank, to_rank, reason, granted_by) VALUES (?, 'member', 'reviewer', 'x', ?)", (CAT, BOB), "grantor")
refused("rank history can't be edited", "UPDATE rank_events SET reason='x'", (), "append-only")
refused("rank history can't be deleted", "DELETE FROM rank_events", (), "append-only")

# threads & posts
refused("member can't open an announcement", "INSERT INTO threads (board_id, member_id, title) VALUES (?, ?, 'hello')", (board("announcements"), BOB), "rank too low")
db.execute("INSERT INTO threads (board_id, member_id, title) VALUES (?, ?, 'Welcome')", (board("announcements"), JW))
db.execute("INSERT INTO posts (thread_id, member_id, body) VALUES (1, ?, 'hi')", (JW,))
db.execute("INSERT INTO posts (thread_id, member_id, body, source, discord_ref) VALUES (1, ?, 'hey', 'discord', 'int-1')", (BOB,))
ok("thread counts posts", q("SELECT post_count FROM threads WHERE id=1")[0] == 2)
refused("same Discord interaction can't double-post", "INSERT INTO posts (thread_id, member_id, body, source, discord_ref) VALUES (1, ?, 'hey', 'discord', 'int-1')", (BOB,), "UNIQUE")
db.execute("UPDATE posts SET body='hey there', edited_at='now' WHERE id=2")
ok("edit keeps the old text", q("SELECT old_body FROM post_revisions WHERE post_id=2")[0] == "hey")
refused("post author can't be changed", "UPDATE posts SET member_id=? WHERE id=2", (JW,), "never change")
refused("posts aren't hard-deleted", "DELETE FROM posts WHERE id=2", (), "soft-deleted")
db.execute("UPDATE threads SET locked=1 WHERE id=1")
refused("locked thread", "INSERT INTO posts (thread_id, member_id, body) VALUES (1, ?, 'x')", (BOB,), "locked")
db.execute("UPDATE members SET banned_at='now', ban_reason='spam' WHERE id=?", (CAT,))
refused("banned can't open threads", "INSERT INTO threads (board_id, member_id, title) VALUES (?, ?, 'spam')", (board("general"), CAT), "banned")

# review board
refused("submission outside the review board", "INSERT INTO submissions (thread_id, member_id, name, sha3_512, bytes, r2_key, custody) VALUES (1, ?, 'x', ?, 10, 'k0', 'verified')", (JW, "a" * 128), "review board")
db.execute("INSERT INTO threads (board_id, member_id, title) VALUES (?, ?, 'romeo.py v2')", (board("peer-review"), BOB))
T = q("SELECT MAX(id) FROM threads")[0]
refused("bad hash", "INSERT INTO submissions (thread_id, member_id, name, sha3_512, bytes, r2_key, custody) VALUES (?, ?, 'romeo.py', 'XYZ', 10, 'k1', 'verified')", (T, BOB))
refused("custody mismatch refused", "INSERT INTO submissions (thread_id, member_id, name, sha3_512, bytes, r2_key, custody) VALUES (?, ?, 'romeo.py', ?, 10, 'k1', 'mismatch')", (T, BOB, "b" * 128), "custody")
refused("over 1 MB refused", "INSERT INTO submissions (thread_id, member_id, name, sha3_512, bytes, r2_key, custody) VALUES (?, ?, 'romeo.py', ?, 2000000, 'k1', 'verified')", (T, BOB, "b" * 128))
refused("someone else's thread", "INSERT INTO submissions (thread_id, member_id, name, sha3_512, bytes, r2_key, custody) VALUES (?, ?, 'romeo.py', ?, 10, 'k1', 'verified')", (T, ANN, "b" * 128), "thread author")
db.execute("INSERT INTO submissions (thread_id, member_id, name, version, sha3_512, bytes, r2_key, custody) VALUES (?, ?, 'romeo.py', 2, ?, 10, 'k1', 'verified')", (T, BOB, "74dd" + "b" * 124))
S = 1
refused("submitted code is immutable", "UPDATE submissions SET sha3_512=? WHERE id=1", ("c" * 128,), "immutable")
refused("status can't be set by hand", "UPDATE submissions SET status='approved' WHERE id=1", (), "decisions")

refused("author can't vote on own code", "INSERT INTO votes (submission_id, member_id, verdict) VALUES (1, ?, 'approve')", (BOB,), "own submission")
refused("members can't vote", "INSERT INTO votes (submission_id, member_id, verdict) VALUES (1, ?, 'approve')", (CAT,))
db.execute("INSERT INTO votes (submission_id, member_id, verdict) VALUES (1, ?, 'reject')", (ANN,))
db.execute("INSERT INTO votes (submission_id, member_id, verdict, note) VALUES (1, ?, 'approve', 'fixed now')", (ANN,))
ok("latest vote counts", q("SELECT verdict FROM current_votes WHERE submission_id=1 AND member_id=?", (ANN,))[0] == "approve")
refused("votes can't be edited", "UPDATE votes SET verdict='reject'", (), "append-only")
refused("votes can't be deleted", "DELETE FROM votes", (), "append-only")

refused("approve with too few votes", "INSERT INTO decisions (submission_id, outcome, reason, approvals, rejections, threshold) VALUES (1, 'approved', 'count', 1, 0, 2)", (), "not enough")
refused("lying about the count", "INSERT INTO decisions (submission_id, outcome, reason, approvals, rejections, threshold) VALUES (1, 'approved', 'count', 2, 0, 2)", (), "do not match")
refused("owner can't force-approve either", "INSERT INTO decisions (submission_id, outcome, decided_by, reason, approvals, rejections, threshold) VALUES (1, 'approved', ?, 'trust me', 1, 0, 2)", (JW,), "not enough")
refused("revoke before approve", "INSERT INTO decisions (submission_id, outcome, decided_by, reason, approvals, rejections, threshold) VALUES (1, 'revoked', ?, 'x', 1, 0, 1)", (JW,), "only after approved")
db.execute("INSERT INTO votes (submission_id, member_id, verdict) VALUES (1, ?, 'approve')", (DAN,))
db.execute("INSERT INTO decisions (submission_id, outcome, reason, approvals, rejections, threshold) VALUES (1, 'approved', 'count', 2, 0, 2)")
ok("approved by the count", q("SELECT status FROM submissions WHERE id=1")[0] == "approved")
ok("author EARNED reviewer", q("SELECT rank FROM members WHERE id=?", (BOB,))[0] == "reviewer")
ok("…with a record and no grantor", q("SELECT granted_by IS NULL AND reason LIKE 'earned:%' FROM rank_events WHERE member_id=? ORDER BY id DESC", (BOB,))[0] == 1)
refused("no votes after a decision", "INSERT INTO votes (submission_id, member_id, verdict) VALUES (1, ?, 'reject')", (ANN,), "closed")
refused("author can't revoke someone's approval of theirs… or decide own", "INSERT INTO decisions (submission_id, outcome, decided_by, reason, approvals, rejections, threshold) VALUES (1, 'revoked', ?, 'x', 2, 0, 1)", (BOB,), "moderator")
db.execute("INSERT INTO decisions (submission_id, outcome, decided_by, reason, approvals, rejections, threshold) VALUES (1, 'revoked', ?, 'leaked a key', 2, 0, 1)", (JW,))
ok("owner revokes with a reason", q("SELECT status FROM submissions WHERE id=1")[0] == "revoked")
refused("decisions can't be edited", "UPDATE decisions SET reason='x'", (), "append-only")
refused("decisions can't be deleted", "DELETE FROM decisions", (), "append-only")
refused("submissions are never deleted", "DELETE FROM submissions", (), "never deleted")

# withdraw
db.execute("INSERT INTO threads (board_id, member_id, title) VALUES (?, ?, 'juliet.py v2')", (board("peer-review"), BOB))
T2 = q("SELECT MAX(id) FROM threads")[0]
db.execute("INSERT INTO submissions (thread_id, member_id, name, sha3_512, bytes, r2_key, custody) VALUES (?, ?, 'juliet.py', ?, 10, 'k2', 'unverified')", (T2, BOB, "d" * 128))
db.execute("UPDATE submissions SET status='withdrawn' WHERE id=2")
ok("author can withdraw while open", q("SELECT status FROM submissions WHERE id=2")[0] == "withdrawn")

print(f"{failed} FAILED, {passed} passed" if failed else f"all {passed} schema rules hold")
sys.exit(1 if failed else 0)
