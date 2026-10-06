-- Phoenix Review — forum + review board. Own D1 (phoenix_review_db).
-- Phoenix DevOps OS | jwl247 | GPL v3
--
-- ProBoards shape: boards → threads → posts, members with earned ranks.
-- The Peer Review board is a board whose threads each carry one submission
-- (code + SHA3-512 custody), votes, and decisions.
--
-- The rules live HERE, in triggers, not only in the worker: a worker bug or a
-- hand-run SQL statement still can't rewrite a vote, forge a decision, approve
-- your own code, or hand out a rank without a record.
--
--   ranks:      member < reviewer < moderator < owner   (rank_events is the only way to change one)
--   votes:      append-only; your latest vote counts; reviewers+ only; never on your own submission
--   decisions:  append-only; "approved" needs enough current approve votes; "revoked" only after approved
--   earned:     your first approved submission makes you a reviewer, automatically, with a record
--   posts:      edits keep the old text in post_revisions; deletes are soft

PRAGMA foreign_keys = ON;

-- ── members & sign-in ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS members (
  id          INTEGER PRIMARY KEY,
  handle      TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (handle NOT GLOB '*[^A-Za-z0-9_-]*' AND length(handle) BETWEEN 3 AND 32),
  display     TEXT NOT NULL CHECK (length(display) BETWEEN 1 AND 64),
  rank        TEXT NOT NULL DEFAULT 'member' CHECK (rank IN ('member','reviewer','moderator','owner')),
  bio         TEXT CHECK (bio IS NULL OR length(bio) <= 2000),
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  banned_at   TEXT,
  ban_reason  TEXT
);

CREATE TABLE IF NOT EXISTS rank_levels (rank TEXT PRIMARY KEY, level INTEGER NOT NULL UNIQUE);
INSERT OR IGNORE INTO rank_levels VALUES ('member',1),('reviewer',2),('moderator',3),('owner',4);

-- Passkeys. Only the PUBLIC key is stored.
CREATE TABLE IF NOT EXISTS credentials (
  id            TEXT PRIMARY KEY,                       -- base64url credential id
  member_id     INTEGER NOT NULL REFERENCES members(id),
  alg           INTEGER NOT NULL CHECK (alg IN (-7, -257)),
  jwk           TEXT NOT NULL CHECK (json_valid(jwk)),
  sign_count    INTEGER NOT NULL DEFAULT 0,
  label         TEXT,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  last_used_at  TEXT,
  revoked_at    TEXT
);
CREATE INDEX IF NOT EXISTS credentials_member ON credentials(member_id);

-- One-shot WebAuthn challenges (5 min). Deleted when used.
CREATE TABLE IF NOT EXISTS challenges (
  id          TEXT PRIMARY KEY,
  purpose     TEXT NOT NULL CHECK (purpose IN ('register','login','add-key')),
  challenge   TEXT NOT NULL UNIQUE,
  member_id   INTEGER REFERENCES members(id),
  pending     TEXT CHECK (pending IS NULL OR json_valid(pending)),   -- handle/display for a new account
  expires_at  TEXT NOT NULL
);

-- Sessions: only the SHA-256 of the cookie token is stored.
CREATE TABLE IF NOT EXISTS sessions (
  token_hash  TEXT PRIMARY KEY CHECK (length(token_hash) = 64),
  member_id   INTEGER NOT NULL REFERENCES members(id),
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  expires_at  TEXT NOT NULL,
  revoked_at  TEXT
);
CREATE INDEX IF NOT EXISTS sessions_member ON sessions(member_id);

-- Every rank change, ever. The ONLY way members.rank changes.
CREATE TABLE IF NOT EXISTS rank_events (
  id          INTEGER PRIMARY KEY,
  member_id   INTEGER NOT NULL REFERENCES members(id),
  from_rank   TEXT NOT NULL,
  to_rank     TEXT NOT NULL CHECK (to_rank IN ('member','reviewer','moderator','owner')),
  reason      TEXT NOT NULL CHECK (length(reason) > 0),
  granted_by  INTEGER REFERENCES members(id),          -- NULL = earned automatically
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TRIGGER IF NOT EXISTS rank_events_from_matches BEFORE INSERT ON rank_events
WHEN NEW.from_rank IS NOT (SELECT rank FROM members WHERE id = NEW.member_id)
BEGIN SELECT RAISE(ABORT, 'rank_events: from_rank does not match the member''s current rank'); END;

CREATE TRIGGER IF NOT EXISTS rank_events_grantor BEFORE INSERT ON rank_events
WHEN NEW.granted_by IS NOT NULL AND (
       NEW.granted_by = NEW.member_id
    OR (SELECT level FROM rank_levels WHERE rank = (SELECT rank FROM members WHERE id = NEW.granted_by)) < 3
    OR ((SELECT rank FROM members WHERE id = NEW.granted_by) <> 'owner'
        AND ((SELECT level FROM rank_levels WHERE rank = NEW.to_rank) >= 3
             OR (SELECT level FROM rank_levels WHERE rank = NEW.from_rank) >= 3)))
BEGIN SELECT RAISE(ABORT, 'rank_events: grantor lacks the rank to make this change (only the owner moves moderators/owners; nobody changes their own rank)'); END;

-- With no grantor, only two changes exist: earning reviewer, and the one-time
-- owner bootstrap (allowed only while the forum has no owner at all).
CREATE TRIGGER IF NOT EXISTS rank_events_ungranted BEFORE INSERT ON rank_events
WHEN NEW.granted_by IS NULL
 AND NOT (NEW.from_rank = 'member' AND NEW.to_rank = 'reviewer')
 AND NOT (NEW.to_rank = 'owner' AND NOT EXISTS (SELECT 1 FROM members WHERE rank = 'owner'))
BEGIN SELECT RAISE(ABORT, 'rank_events: this change needs a grantor'); END;

CREATE TRIGGER IF NOT EXISTS rank_events_apply AFTER INSERT ON rank_events
BEGIN UPDATE members SET rank = NEW.to_rank WHERE id = NEW.member_id; END;

CREATE TRIGGER IF NOT EXISTS members_rank_only_via_events BEFORE UPDATE OF rank ON members
WHEN NEW.rank IS NOT OLD.rank
 AND NEW.rank IS NOT (SELECT to_rank FROM rank_events WHERE member_id = NEW.id ORDER BY id DESC LIMIT 1)
BEGIN SELECT RAISE(ABORT, 'members.rank changes only through rank_events'); END;

CREATE TRIGGER IF NOT EXISTS rank_events_append_only_u BEFORE UPDATE ON rank_events
BEGIN SELECT RAISE(ABORT, 'rank_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS rank_events_append_only_d BEFORE DELETE ON rank_events
BEGIN SELECT RAISE(ABORT, 'rank_events is append-only'); END;

-- ── boards, threads, posts ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS boards (
  id                  INTEGER PRIMARY KEY,
  slug                TEXT NOT NULL UNIQUE CHECK (slug NOT GLOB '*[^a-z0-9-]*' AND length(slug) BETWEEN 2 AND 40),
  name                TEXT NOT NULL,
  description         TEXT NOT NULL DEFAULT '',
  kind                TEXT NOT NULL CHECK (kind IN ('discussion','review','announce')),
  position            INTEGER NOT NULL DEFAULT 0,
  min_rank_thread     TEXT NOT NULL DEFAULT 'member' REFERENCES rank_levels(rank),
  min_rank_reply      TEXT NOT NULL DEFAULT 'member' REFERENCES rank_levels(rank),
  discord_channel_id  TEXT
);
INSERT OR IGNORE INTO boards (slug, name, description, kind, position, min_rank_thread, min_rank_reply) VALUES
  ('announcements', 'Announcements', 'News from the Phoenix project.',                                  'announce',   1, 'owner',  'member'),
  ('general',       'General',       'Anything Phoenix.',                                                'discussion', 2, 'member', 'member'),
  ('help',          'Help',          'Stuck? Ask here.',                                                 'discussion', 3, 'member', 'member'),
  ('peer-review',   'Peer Review',   'Submit code for review. Each thread is one submission: the code, the discussion, the votes.', 'review', 4, 'member', 'member');

CREATE TABLE IF NOT EXISTS threads (
  id                 INTEGER PRIMARY KEY,
  board_id           INTEGER NOT NULL REFERENCES boards(id),
  member_id          INTEGER NOT NULL REFERENCES members(id),
  title              TEXT NOT NULL CHECK (length(title) BETWEEN 3 AND 160),
  created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  last_post_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  post_count         INTEGER NOT NULL DEFAULT 0,
  pinned             INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0,1)),
  locked             INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0,1)),
  discord_thread_id  TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS threads_board ON threads(board_id, pinned DESC, last_post_at DESC);

CREATE TABLE IF NOT EXISTS posts (
  id           INTEGER PRIMARY KEY,
  thread_id    INTEGER NOT NULL REFERENCES threads(id),
  member_id    INTEGER NOT NULL REFERENCES members(id),
  body         TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 20000),
  source       TEXT NOT NULL DEFAULT 'web' CHECK (source IN ('web','discord','phoenix','system')),
  discord_ref  TEXT UNIQUE,                               -- interaction id: a retried Discord call can't double-post
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  edited_at    TEXT,
  deleted_at   TEXT,
  deleted_by   INTEGER REFERENCES members(id)
);
CREATE INDEX IF NOT EXISTS posts_thread ON posts(thread_id, id);

CREATE TABLE IF NOT EXISTS post_revisions (
  id          INTEGER PRIMARY KEY,
  post_id     INTEGER NOT NULL REFERENCES posts(id),
  old_body    TEXT NOT NULL,
  replaced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- posting rules enforced in the database
CREATE TRIGGER IF NOT EXISTS posts_rules BEFORE INSERT ON posts
BEGIN
  SELECT RAISE(ABORT, 'banned members cannot post')
   WHERE (SELECT banned_at FROM members WHERE id = NEW.member_id) IS NOT NULL;
  SELECT RAISE(ABORT, 'thread is locked')
   WHERE (SELECT locked FROM threads WHERE id = NEW.thread_id) = 1;
  SELECT RAISE(ABORT, 'rank too low to reply on this board')
   WHERE (SELECT level FROM rank_levels WHERE rank = (SELECT rank FROM members WHERE id = NEW.member_id))
       < (SELECT l.level FROM threads t JOIN boards b ON b.id = t.board_id JOIN rank_levels l ON l.rank = b.min_rank_reply WHERE t.id = NEW.thread_id);
END;

CREATE TRIGGER IF NOT EXISTS threads_rules BEFORE INSERT ON threads
BEGIN
  SELECT RAISE(ABORT, 'banned members cannot post')
   WHERE (SELECT banned_at FROM members WHERE id = NEW.member_id) IS NOT NULL;
  SELECT RAISE(ABORT, 'rank too low to start a thread on this board')
   WHERE (SELECT level FROM rank_levels WHERE rank = (SELECT rank FROM members WHERE id = NEW.member_id))
       < (SELECT l.level FROM boards b JOIN rank_levels l ON l.rank = b.min_rank_thread WHERE b.id = NEW.board_id);
END;

CREATE TRIGGER IF NOT EXISTS posts_count AFTER INSERT ON posts
BEGIN UPDATE threads SET post_count = post_count + 1, last_post_at = NEW.created_at WHERE id = NEW.thread_id; END;

CREATE TRIGGER IF NOT EXISTS posts_keep_history BEFORE UPDATE OF body ON posts
WHEN NEW.body IS NOT OLD.body
BEGIN INSERT INTO post_revisions (post_id, old_body) VALUES (OLD.id, OLD.body); END;

CREATE TRIGGER IF NOT EXISTS posts_fixed_fields BEFORE UPDATE ON posts
WHEN NEW.thread_id IS NOT OLD.thread_id OR NEW.member_id IS NOT OLD.member_id
  OR NEW.created_at IS NOT OLD.created_at OR NEW.source IS NOT OLD.source
BEGIN SELECT RAISE(ABORT, 'a post''s thread, author, time and source never change'); END;

CREATE TRIGGER IF NOT EXISTS posts_no_hard_delete BEFORE DELETE ON posts
BEGIN SELECT RAISE(ABORT, 'posts are soft-deleted (set deleted_at)'); END;
CREATE TRIGGER IF NOT EXISTS revisions_append_only_u BEFORE UPDATE ON post_revisions
BEGIN SELECT RAISE(ABORT, 'post_revisions is append-only'); END;
CREATE TRIGGER IF NOT EXISTS revisions_append_only_d BEFORE DELETE ON post_revisions
BEGIN SELECT RAISE(ABORT, 'post_revisions is append-only'); END;

-- ── review board: submissions, votes, decisions ──────────────────────────────
CREATE TABLE IF NOT EXISTS submissions (
  id           INTEGER PRIMARY KEY,
  thread_id    INTEGER NOT NULL UNIQUE REFERENCES threads(id),
  member_id    INTEGER NOT NULL REFERENCES members(id),
  name         TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  version      INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  hex_id       TEXT,                                     -- Phoenix custody identity, when it came through intake
  sha3_512     TEXT NOT NULL CHECK (length(sha3_512) = 128 AND sha3_512 NOT GLOB '*[^0-9a-f]*'),
  bytes        INTEGER NOT NULL CHECK (bytes BETWEEN 1 AND 1048576),
  r2_key       TEXT NOT NULL UNIQUE,
  language     TEXT,
  custody      TEXT NOT NULL CHECK (custody IN ('verified','unverified','mismatch')),
  status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','approved','rejected','revoked','withdrawn')),
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TRIGGER IF NOT EXISTS submissions_on_review_board BEFORE INSERT ON submissions
BEGIN
  SELECT RAISE(ABORT, 'submissions live only on the review board')
   WHERE (SELECT b.kind FROM threads t JOIN boards b ON b.id = t.board_id WHERE t.id = NEW.thread_id) IS NOT 'review';
  SELECT RAISE(ABORT, 'submission author must be the thread author')
   WHERE (SELECT member_id FROM threads WHERE id = NEW.thread_id) IS NOT NEW.member_id;
  SELECT RAISE(ABORT, 'custody mismatch: bytes differ from Phoenix custody, refused')
   WHERE NEW.custody = 'mismatch';
END;

-- What gets reviewed never changes: new code = new submission.
CREATE TRIGGER IF NOT EXISTS submissions_fixed BEFORE UPDATE ON submissions
WHEN NEW.sha3_512 IS NOT OLD.sha3_512 OR NEW.r2_key IS NOT OLD.r2_key OR NEW.bytes IS NOT OLD.bytes
  OR NEW.member_id IS NOT OLD.member_id OR NEW.thread_id IS NOT OLD.thread_id OR NEW.name IS NOT OLD.name
  OR NEW.version IS NOT OLD.version
BEGIN SELECT RAISE(ABORT, 'submitted code is immutable; submit a new version instead'); END;

CREATE TRIGGER IF NOT EXISTS submissions_status_via_decisions BEFORE UPDATE OF status ON submissions
WHEN NEW.status IS NOT OLD.status AND NOT (
       (NEW.status = 'withdrawn' AND OLD.status = 'open')
    OR NEW.status IS (SELECT outcome FROM decisions WHERE submission_id = NEW.id ORDER BY id DESC LIMIT 1))
BEGIN SELECT RAISE(ABORT, 'submission status changes only through decisions (or withdraw while open)'); END;

CREATE TRIGGER IF NOT EXISTS submissions_no_delete BEFORE DELETE ON submissions
BEGIN SELECT RAISE(ABORT, 'submissions are never deleted'); END;

CREATE TABLE IF NOT EXISTS votes (
  id             INTEGER PRIMARY KEY,
  submission_id  INTEGER NOT NULL REFERENCES submissions(id),
  member_id      INTEGER NOT NULL REFERENCES members(id),
  verdict        TEXT NOT NULL CHECK (verdict IN ('approve','needs-work','reject')),
  note           TEXT CHECK (note IS NULL OR length(note) <= 4000),
  created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS votes_sub ON votes(submission_id, member_id, id);

CREATE TRIGGER IF NOT EXISTS votes_rules BEFORE INSERT ON votes
BEGIN
  SELECT RAISE(ABORT, 'you cannot vote on your own submission')
   WHERE NEW.member_id = (SELECT member_id FROM submissions WHERE id = NEW.submission_id);
  SELECT RAISE(ABORT, 'voting is for reviewers and up')
   WHERE (SELECT level FROM rank_levels WHERE rank = (SELECT rank FROM members WHERE id = NEW.member_id)) < 2;
  SELECT RAISE(ABORT, 'banned members cannot vote')
   WHERE (SELECT banned_at FROM members WHERE id = NEW.member_id) IS NOT NULL;
  SELECT RAISE(ABORT, 'voting is closed on this submission')
   WHERE (SELECT status FROM submissions WHERE id = NEW.submission_id) IS NOT 'open';
END;
CREATE TRIGGER IF NOT EXISTS votes_append_only_u BEFORE UPDATE ON votes
BEGIN SELECT RAISE(ABORT, 'votes are append-only; vote again to change your vote'); END;
CREATE TRIGGER IF NOT EXISTS votes_append_only_d BEFORE DELETE ON votes
BEGIN SELECT RAISE(ABORT, 'votes are append-only'); END;

-- Each reviewer's latest vote, from reviewers who are still eligible.
CREATE VIEW IF NOT EXISTS current_votes AS
SELECT v.* FROM votes v
JOIN members m ON m.id = v.member_id
WHERE v.id = (SELECT MAX(id) FROM votes WHERE submission_id = v.submission_id AND member_id = v.member_id)
  AND m.banned_at IS NULL
  AND (SELECT level FROM rank_levels WHERE rank = m.rank) >= 2;

CREATE TABLE IF NOT EXISTS decisions (
  id             INTEGER PRIMARY KEY,
  submission_id  INTEGER NOT NULL REFERENCES submissions(id),
  outcome        TEXT NOT NULL CHECK (outcome IN ('approved','rejected','revoked')),
  decided_by     INTEGER REFERENCES members(id),          -- NULL = the vote count decided it
  reason         TEXT NOT NULL CHECK (length(reason) > 0),
  approvals      INTEGER NOT NULL,
  rejections     INTEGER NOT NULL,
  threshold      INTEGER NOT NULL CHECK (threshold >= 1),
  created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TRIGGER IF NOT EXISTS decisions_rules BEFORE INSERT ON decisions
BEGIN
  SELECT RAISE(ABORT, 'approved/rejected only while open')
   WHERE NEW.outcome IN ('approved','rejected') AND (SELECT status FROM submissions WHERE id = NEW.submission_id) IS NOT 'open';
  SELECT RAISE(ABORT, 'revoked only after approved')
   WHERE NEW.outcome = 'revoked' AND (SELECT status FROM submissions WHERE id = NEW.submission_id) IS NOT 'approved';
  -- the recorded counts must be the real counts
  SELECT RAISE(ABORT, 'decision counts do not match current votes')
   WHERE NEW.approvals  IS NOT (SELECT COUNT(*) FROM current_votes WHERE submission_id = NEW.submission_id AND verdict = 'approve')
      OR NEW.rejections IS NOT (SELECT COUNT(*) FROM current_votes WHERE submission_id = NEW.submission_id AND verdict = 'reject');
  -- nobody, owner included, approves code without enough reviewers saying yes
  SELECT RAISE(ABORT, 'not enough approvals')
   WHERE NEW.outcome = 'approved' AND (NEW.approvals < NEW.threshold OR NEW.rejections > 0);
  -- a person deciding by hand must be a moderator+ and not the author
  SELECT RAISE(ABORT, 'manual decisions need a moderator or owner who is not the author')
   WHERE NEW.decided_by IS NOT NULL AND (
         NEW.decided_by = (SELECT member_id FROM submissions WHERE id = NEW.submission_id)
      OR (SELECT level FROM rank_levels WHERE rank = (SELECT rank FROM members WHERE id = NEW.decided_by)) < 3);
  SELECT RAISE(ABORT, 'rejected/revoked by the count needs a rejection vote')
   WHERE NEW.decided_by IS NULL AND NEW.outcome IN ('rejected','revoked') AND NEW.rejections = 0;
END;

CREATE TRIGGER IF NOT EXISTS decisions_apply AFTER INSERT ON decisions
BEGIN
  UPDATE submissions SET status = NEW.outcome WHERE id = NEW.submission_id;
  -- earned rank: first approved submission makes a member a reviewer
  INSERT INTO rank_events (member_id, from_rank, to_rank, reason, granted_by)
  SELECT s.member_id, 'member', 'reviewer', 'earned: first approved submission #' || s.id, NULL
    FROM submissions s JOIN members m ON m.id = s.member_id
   WHERE s.id = NEW.submission_id AND NEW.outcome = 'approved' AND m.rank = 'member';
END;

CREATE TRIGGER IF NOT EXISTS decisions_append_only_u BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_append_only_d BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;

-- ── Discord ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS discord_links (
  member_id     INTEGER PRIMARY KEY REFERENCES members(id),
  discord_id    TEXT NOT NULL UNIQUE,
  discord_name  TEXT NOT NULL,
  linked_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS link_codes (
  code        TEXT PRIMARY KEY CHECK (length(code) = 8),
  member_id   INTEGER NOT NULL REFERENCES members(id),
  expires_at  TEXT NOT NULL,
  used_at     TEXT
);

-- Forum → Discord messages wait here; a cron drains it, so Discord being down loses nothing.
CREATE TABLE IF NOT EXISTS discord_outbox (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL CHECK (kind IN ('thread','post','decision','rank')),
  thread_id   INTEGER REFERENCES threads(id),
  content     TEXT NOT NULL,
  attempts    INTEGER NOT NULL DEFAULT 0,
  last_error  TEXT,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  sent_at     TEXT
);
CREATE INDEX IF NOT EXISTS outbox_pending ON discord_outbox(sent_at, id);

-- ── settings ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO settings VALUES ('approvals_needed_max', '2'), ('schema_version', '1');
