#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# phone-setup.sh — Life First phone node (Termux, from F-Droid)
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Stage 1 (default): the phone client — eyes, ears, screen.
#   packages -> keys (hidden prompt, owner-only file, never on a command line)
#   -> phoenix_phone.py pulled from the clonepool and SHA3-512-checked against
#   D1 custody -> phone.env -> listener started at boot (Termux:Boot).
# Stage 2 (--with-kernel): proot Debian + python3 + PowerShell 7 (arm64), the
#   home of the phone's own small kernel. Stops before cloning the kernel tree:
#   that needs the sector1/sector4 trees intaked as verified directory
#   snapshots first (2026-10-03: `sector1` is one of the 86 rows with no hash).
#
# Needs: the Tailscale app on the phone, signed in to the Phoenix tailnet
# (the brain's address below is its MESH address, never a LAN/public IP);
# the Termux:API app; the Termux:Boot app (for start-at-boot).
#
#   bash phone-setup.sh [--with-kernel]
# Re-runnable: keeps existing keys/config unless you choose to replace them.
# =============================================================================
set -euo pipefail

WORKER_URL="${PHOENIX_WORKER_URL:-https://packages-worker.phoenix-jwl.workers.dev}"
PHX="$HOME/.phoenix"
SECRETS="$PHX/worker.headers"        # curl header file, chmod 600
ENV_FILE="$PHX/phone.env"            # phoenix_phone.py config, chmod 600
BIN="$PHX/bin"
CLIENT="$BIN/phoenix_phone.py"
PWSH_VERSION="${PWSH_VERSION:-7.4.6}"
WITH_KERNEL=0
[[ "${1:-}" == "--with-kernel" ]] && WITH_KERNEL=1

say()  { printf '  [phone] %s\n' "$*"; }
fail() { printf '  [phone] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -d /data/data/com.termux ]] || fail "run this inside Termux (F-Droid build)"
umask 077
mkdir -p "$PHX" "$BIN"

# ── 1. packages ──────────────────────────────────────────────────────────────
say "installing packages (python, termux-api, curl)"
pkg update -y >/dev/null
pkg install -y python termux-api curl procps >/dev/null
command -v termux-notification >/dev/null || fail "termux-api missing"
termux-notification --title "Phoenix" --content "phone setup running" --id phoenix-setup >/dev/null 2>&1 \
  || say "WARNING: notifications failed — install the Termux:API app and allow notifications"

# ── 2. keys: hidden prompt -> owner-only header file ────────────────────────
write_headers() {
  local auth cfid cfsec
  read -rsp "  PHOENIX_AUTH: " auth; echo
  read -rsp "  CF_ACCESS_CLIENT_ID: " cfid; echo
  read -rsp "  CF_ACCESS_CLIENT_SECRET: " cfsec; echo
  [[ -n "$auth" && -n "$cfid" && -n "$cfsec" ]] || fail "all three keys are required"
  printf 'Authorization: Bearer %s\nCF-Access-Client-Id: %s\nCF-Access-Client-Secret: %s\n' \
    "$auth" "$cfid" "$cfsec" > "$SECRETS"
  chmod 600 "$SECRETS"
}
if [[ -s "$SECRETS" ]]; then
  read -rp "  worker keys already saved — replace them? [y/N] " a
  [[ "$a" =~ ^[Yy]$ ]] && write_headers
else
  say "worker keys (typed hidden, saved to $SECRETS, mode 600)"
  write_headers
fi

# curl reads headers from the file (-H @file): keys never appear in ps/argv.
worker() { curl -fsS --max-time 60 -H @"$SECRETS" "$@"; }
say "checking worker auth"
worker "$WORKER_URL/whoami" >/dev/null || fail "worker refused the keys (wrong PHOENIX_AUTH or CF Access token?)"

# ── 3. client from the clonepool, custody-checked ───────────────────────────
clone_verified() {   # clone_verified <name> <dest>
  local name="$1" dest="$2" hex meta want got tmp
  hex=$(printf '%s' "$name" | od -An -tx1 | tr -d ' \n')       # intake.sh's to_hex(basename)
  meta=$(worker "$WORKER_URL/clonepool/$hex?meta=true") || fail "$name not in the clonepool — intake it on PBMII first"
  want=$(printf '%s' "$meta" | python -c 'import json,sys; print((json.load(sys.stdin).get("hash_sha3") or "").lower())')
  [[ "$want" =~ ^[0-9a-f]{128}$ ]] || fail "$name has no SHA3 baseline in D1 — re-intake it on PBMII"
  tmp="$dest.part"
  worker -o "$tmp" -D "$PHX/.hdr" "$WORKER_URL/clonepool/$hex" || fail "download of $name failed"
  grep -qi '^content-type: application/octet-stream' "$PHX/.hdr" || { rm -f "$tmp"; fail "$name: R2 has no bytes (worker sent metadata only)"; }
  got=$(python -c 'import hashlib,sys; print(hashlib.sha3_512(open(sys.argv[1],"rb").read()).hexdigest())' "$tmp")
  if [[ "$got" != "$want" ]]; then rm -f "$tmp"; fail "$name: SHA3-512 MISMATCH against custody — not installed"; fi
  mv -f "$tmp" "$dest"; rm -f "$PHX/.hdr"
  say "$name verified (sha3 ${got:0:16}…) -> $dest"
}
clone_verified phoenix_phone.py "$CLIENT"
chmod 700 "$CLIENT"

# ── 4. phone.env ────────────────────────────────────────────────────────────
if [[ -s "$ENV_FILE" ]]; then
  say "keeping existing $ENV_FILE"
else
  read -rp "  brain's Phoenix Mesh (Tailscale) address, e.g. 100.x.y.z: " brain
  [[ "$brain" =~ ^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}$ || "$brain" == *.ts.net ]] \
    || fail "$brain is not a Tailscale address (100.64.0.0/10 or *.ts.net) — the Helix sockets only face the mesh"
  read -rsp "  HELIX_SOCKET_TOKEN (same as the brain's): " tok; echo
  read -rp "  whose phone is this (e.g. laurie): " who
  read -rp "  speak replies out loud? [y/N] " sp
  { printf 'PHOENIX_BRAIN=%s\nHELIX_SOCKET_TOKEN=%s\nPHOENIX_WHO=%s\n' "$brain" "$tok" "$who"
    [[ "$sp" =~ ^[Yy]$ ]] && printf 'PHOENIX_SPEAK=1\n'; } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

# ── 5. shortcuts + start at boot ────────────────────────────────────────────
cat > "$PREFIX/bin/lifefirst" <<EOF
#!$PREFIX/bin/bash
exec python "$CLIENT" "\$@"
EOF
chmod 700 "$PREFIX/bin/lifefirst"
mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/phoenix-listen" <<EOF
#!$PREFIX/bin/bash
termux-wake-lock
exec python "$CLIENT" listen >> "$PHX/phone/listen.log" 2>&1
EOF
chmod 700 "$HOME/.termux/boot/phoenix-listen"
mkdir -p "$PHX/phone"
say "start-at-boot installed (needs the Termux:Boot app, opened once)"

say "doctor:"
python "$CLIENT" doctor || say "doctor found problems above — fix them, then: lifefirst doctor"
if ! pgrep -f "phoenix_phone.py listen" >/dev/null; then
  nohup "$HOME/.termux/boot/phoenix-listen" >/dev/null 2>&1 &
  say "listener started"
fi

# ── stage 2: proot Debian + PS7 for the phone's own kernel ──────────────────
if [[ "$WITH_KERNEL" -eq 1 ]]; then
  say "stage 2: proot Debian + python3 + PowerShell $PWSH_VERSION (arm64)"
  pkg install -y proot-distro >/dev/null
  proot-distro list 2>/dev/null | grep -q 'debian.*installed' || proot-distro install debian
  proot-distro login debian -- bash -euo pipefail -c "
    apt-get update -qq
    apt-get install -y -qq python3 curl ca-certificates libicu72 >/dev/null 2>&1 || apt-get install -y -qq python3 curl ca-certificates libicu-dev >/dev/null
    if ! command -v pwsh >/dev/null; then
      curl -fsSL -o /tmp/pwsh.tgz https://github.com/PowerShell/PowerShell/releases/download/v$PWSH_VERSION/powershell-$PWSH_VERSION-linux-arm64.tar.gz
      mkdir -p /opt/microsoft/powershell/7 && tar xzf /tmp/pwsh.tgz -C /opt/microsoft/powershell/7
      chmod +x /opt/microsoft/powershell/7/pwsh && ln -sf /opt/microsoft/powershell/7/pwsh /usr/local/bin/pwsh
      rm -f /tmp/pwsh.tgz
    fi
    pwsh -NoProfile -c '\$PSVersionTable.PSVersion.ToString()'
  "
  say "stage 2 ready: proot-distro login debian, then pwsh."
  say "NOT done yet: cloning the kernel tree — intake sector1/ and sector4/ as verified directory snapshots on PBMII first."
fi

say "done. Try:  lifefirst say \"testing from my phone\""
