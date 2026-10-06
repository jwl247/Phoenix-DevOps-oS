#!/usr/bin/env bash
# =============================================================================
# sync-standalone.sh — Phoenix keeps the public Phoenix-Package_handler repo in
# sync with the canonical copy, sector2/package-handler in Phoenix-DevOps-oS.
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   bash sector2/package-handler/sync-standalone.sh           dry run: build + show the diff
#   bash sector2/package-handler/sync-standalone.sh --push    build, gate, commit, push
#
# Why: the standalone repo is what fresh installs and the public one-liners in
# README.md pull (install.ps1 clones it; `curl …/install.sh | bash`). It was
# archived on 2026-09-13 and nothing ever synced it, so every new install got
# intake.sh 1.6.0 (SHA3-256, no version ledger) while production runs 1.7.0.
#
# What it does, in order:
#   1. Takes sector2/package-handler from the monorepo's HEAD (committed code
#      only — `git archive`, LF line endings, never the working tree).
#   2. Clones the standalone repo and replaces its tree with an ALLOWLIST of
#      files. Phoenix-internal data never goes out (atlas-sources.json is every
#      CONNECTIONS.md in the monorepo; connections-seed.json, push-context, the
#      retired r2-worker, the monorepo-only Atlas scripts).
#   3. Keeps the public copy un-deployable: worker name forced to the
#      do-not-deploy name, and no .github workflow (deploys happen from the
#      monorepo only — a deploy workflow in a public repo is how the live
#      packages-worker could be overwritten by a push).
#   4. Gates: bash -n on every shell script, node --check on the worker, and a
#      secret scan — patterns for tokens/keys PLUS the literal values of
#      PHOENIX_AUTH / CF_ACCESS_CLIENT_SECRET / CF_ACCESS_CLIENT_ID if they are
#      set in this shell (read from a 0600 temp file, never from argv).
#      Any hit = no commit, no push.
#   5. Commits "sync: Phoenix-DevOps-oS@<sha>" and, with --push, pushes.
#
# Env: PHX_STANDALONE_REMOTE (default https://github.com/jwl247/Phoenix-Package_handler.git)
#      PHX_STANDALONE_BRANCH (default main)
# =============================================================================
set -euo pipefail

PUSH=0
case "${1:-}" in
  --push) PUSH=1 ;;
  ""|--dry-run) ;;
  -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
  *) echo "usage: $0 [--push]" >&2; exit 2 ;;
esac

REMOTE="${PHX_STANDALONE_REMOTE:-https://github.com/jwl247/Phoenix-Package_handler.git}"
BRANCH="${PHX_STANDALONE_BRANCH:-main}"
SAFE_NAME="packages-worker-standalone-do-not-deploy-see-comment"

ALLOW=(
  intake.sh
  install.sh
  install.ps1
  uninstall.ps1
  rotate-phoenix-auth.sh
  backfill-versions.py
  pool-tidy.py
  README.md
  PEER_REVIEW.md
  .gitignore
  peer-review/schema.sql
  worker/index.js
  worker/atlas-parse.mjs
  worker/schema-d1.sql
  worker/schema-connections.sql
  worker/wrangler.jsonc
)

say()  { printf '  [sync] %s\n' "$*"; }
fail() { printf '  [sync] STOP: %s\n' "$*" >&2; exit 1; }

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(git -C "$here" rev-parse --show-toplevel 2>/dev/null)" || fail "not inside the Phoenix-DevOps-oS git repo"
sub="$(git -C "$here" rev-parse --show-prefix)"; sub="${sub%/}"
[[ -n "$sub" ]] || fail "run the copy inside sector2/package-handler, not a standalone checkout"
sha="$(git -C "$root" rev-parse --short=12 HEAD)"
if [[ -n "$(git -C "$root" status --porcelain -- "$sub")" ]]; then
  say "WARNING: uncommitted changes under $sub — they are NOT synced (HEAD $sha only)"
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/src"

# 1. committed code only
git -C "$root" archive --format=tar HEAD "$sub" | tar -x -C "$work/src"
src="$work/src/$sub"
for f in "${ALLOW[@]}"; do
  [[ -f "$src/$f" ]] || fail "$f is in the allowlist but not committed at HEAD under $sub"
done

# 2. standalone checkout, tree replaced by the allowlist
say "cloning $REMOTE ($BRANCH)"
git clone -q --branch "$BRANCH" "$REMOTE" "$work/dst" || fail "could not clone $REMOTE"
dst="$work/dst"
before="$(git -C "$dst" rev-parse --short=12 HEAD)"
find "$dst" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
for f in "${ALLOW[@]}"; do
  mkdir -p "$dst/$(dirname "$f")"
  cp "$src/$f" "$dst/$f"
done
chmod +x "$dst"/*.sh 2>/dev/null || true

# 3. keep it un-deployable
python3 - "$dst/worker/wrangler.jsonc" "$SAFE_NAME" <<'PY' || fail "could not rewrite the worker name"
import re, sys
p, safe = sys.argv[1], sys.argv[2]
s = open(p, encoding="utf-8").read()
s, n = re.subn(r'^(\s*"name"\s*:\s*)"[^"]*"', r'\1"' + safe + '"', s, count=1, flags=re.M)
if n != 1:
    sys.exit("no top-level \"name\" in wrangler.jsonc")
head = ("// STANDALONE MIRROR — DO NOT DEPLOY. Synced from Phoenix-DevOps-oS/sector2/package-handler\n"
        "// by sync-standalone.sh. The live packages-worker deploys from the monorepo only; the\n"
        "// name below is deliberately not \"packages-worker\" so a deploy from here can't overwrite it.\n")
open(p, "w", encoding="utf-8", newline="\n").write(head + s)
PY
grep -q "\"name\": *\"$SAFE_NAME\"" "$dst/worker/wrangler.jsonc" || fail "worker name is not the do-not-deploy name"

cat > "$dst/CONNECTIONS.md" <<EOF
# Phoenix-Package_handler — public mirror

Synced from \`Phoenix-DevOps-oS/sector2/package-handler\` at \`$sha\` by \`sync-standalone.sh\`.
That copy is the source of truth: change it there, then sync. Changes made only here are
overwritten by the next sync.

- \`intake.sh\` — intake (IN) / clone (OUT) pipeline: hex identity, sidecar, T1–T4 pool, D1 custody
  and version ledger, R2 bytes, SHA3-512 + BLAKE2b integrity.
- \`worker/\` — packages-worker source (clonepool, glossary, custody, versions, Atlas). This mirror
  is named so it can't deploy over the live worker.
- \`install.sh\` / \`install.ps1\` / \`uninstall.ps1\` — set up the \`intake\` command.
EOF

# 4. gates
for f in "$dst"/*.sh; do bash -n "$f" || fail "bash syntax error in $(basename "$f")"; done
if command -v node >/dev/null 2>&1; then
  for f in worker/index.js worker/atlas-parse.mjs; do
    cp "$dst/$f" "$work/check.mjs"
    node --check "$work/check.mjs" || fail "JavaScript syntax error in $f"
  done
else
  say "node not found — worker syntax gate skipped"
fi

hits="$work/hits.txt"; : > "$hits"
grep -rInE \
  -e 'Bearer [A-Za-z0-9._~+/=-]{24,}' \
  -e '(PHOENIX_AUTH|CF_ACCESS_CLIENT_SECRET|CF_ACCESS_CLIENT_ID|CLOUDFLARE_API_TOKEN|STRIPE_[A-Z_]*KEY[A-Z_]*)[[:space:]]*[=:][[:space:]]*["'"'"']?[A-Za-z0-9._-]{20,}' \
  -e '[0-9a-f]{32}\.access' \
  -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
  -e '(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}' \
  -e 'sk_(live|test)_[A-Za-z0-9]{16,}' \
  --exclude-dir=.git "$dst" >> "$hits" || true
vals="$work/vals.txt"; : > "$vals"; chmod 600 "$vals"
for v in PHOENIX_AUTH CF_ACCESS_CLIENT_SECRET CF_ACCESS_CLIENT_ID; do
  [[ -n "${!v:-}" ]] && printf '%s\n' "${!v}" >> "$vals"
done
if [[ -s "$vals" ]]; then
  grep -rlF -f "$vals" --exclude-dir=.git "$dst" | sed 's/$/: contains a live key value/' >> "$hits" || true
fi
if [[ -s "$hits" ]]; then
  sed "s|$dst/||" "$hits" | cut -c1-160 >&2
  fail "secret scan hit — nothing committed, nothing pushed"
fi
say "gates passed: shell syntax, worker syntax, secret scan"

# 5. commit (+ push)
git -C "$dst" add -A
if git -C "$dst" diff --cached --quiet; then
  say "standalone already matches Phoenix-DevOps-oS@$sha — nothing to sync"
  exit 0
fi
git -C "$dst" diff --cached --stat | tail -25
git -C "$dst" -c user.name="$(git -C "$root" config user.name || echo Phoenix)" \
             -c user.email="$(git -C "$root" config user.email || echo phoenix@localhost)" \
  commit -q -m "sync: Phoenix-DevOps-oS@$sha sector2/package-handler" \
            -m "Published by sync-standalone.sh (allowlist, do-not-deploy worker name, no deploy workflow, secret-scanned)."
after="$(git -C "$dst" rev-parse --short=12 HEAD)"
if [[ "$PUSH" -eq 1 ]]; then
  git -C "$dst" push -q origin "HEAD:$BRANCH" || fail "push refused — check your GitHub credentials for $REMOTE"
  say "pushed $before → $after to $REMOTE ($BRANCH)"
else
  say "dry run: would push $before → $after. Run again with --push to publish."
fi
