#!/usr/bin/env bash
# install-jarvis.sh — Jarvis (OpenJarvis on the local llama.cpp engine) on a Phoenix Debian box, with rails.
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Run as root on the box (pbmIII), from a folder holding this sector2/apps/jarvis/ set:
#   sudo bash install-jarvis.sh <openjarvis-src.tar.gz> <llama-server> <model.gguf> <caller-pubkey> [more pubkeys...]
# Get the engine and the model from the clone pool (import, don't download): `intake clone llama-server-avx`
# (or -baseline on a CPU without AVX) and `intake clone llama3.2-3b-q4km.gguf`.
# One key per calling box (PBMII, awslh, ...); each gets the same forced command. Re-runnable.
#
# Rails (Jerry 2026-10-06/07: "no spies"):
#   - every artifact must match pins.sha256 or nothing is installed
#   - the engine is llama.cpp built with HTTPS compiled out; Ollama is NOT used (it phoned home)
#   - both services: own nologin user, localhost only, IPAddressDeny=any (no traffic out at all)
#   - both APIs need a key; keys are generated here, never in git, never printed
#   - no analytics, no skills marketplace, no tools; callers come in ONLY through jarvis-gate (SSH forced command, mesh only)
set -euo pipefail
SRC=${1:?openjarvis source tarball}; ENGINE=${2:?llama-server binary}; MODEL=${3:?model .gguf}; shift 3
[[ $# -ge 1 ]] || { echo "need at least one caller public key file"; exit 1; }
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd); O=/opt/openjarvis

# ── 1. Pins: refuse anything that isn't the exact bytes we vetted ──────────────────────────────
pin() {  # pin <file> <name-in-pins.sha256>
  local want got
  want=$(awk -v n="$2" '$2==n {print $1}' "$HERE/pins.sha256")
  [[ -n "$want" ]] || { echo "no pin for $2 in pins.sha256 - refusing"; exit 1; }
  got=$(sha256sum "$1" | awk '{print $1}')
  [[ "$got" == "$want" ]] || { echo "PIN MISMATCH: $1 is $got, pins.sha256 says $want for $2 - refusing"; exit 1; }
  echo "pin ok: $2"
}
pin "$SRC" openjarvis-src.tar.gz
pin "$MODEL" llama3.2-3b-q4km.gguf
# which engine build is this? (no pipeline/&& tricks: a non-match must not trip set -e silently)
ENGINE_SHA=$(sha256sum "$ENGINE" | awk '{print $1}')
ENGINE_PIN=$(awk -v h="$ENGINE_SHA" '$1==h && $2 ~ /^llama-server-/ {print $2; exit}' "$HERE/pins.sha256")
[[ -n "$ENGINE_PIN" ]] || { echo "PIN MISMATCH: $ENGINE matches no llama-server-* pin - refusing"; exit 1; }
echo "pin ok: $ENGINE_PIN"
if [[ "$ENGINE_PIN" == *-avx ]] && ! grep -qw avx /proc/cpuinfo; then
  echo "this CPU has no AVX: use the llama-server-baseline build"; exit 1
fi

# ── 2. Users and the engine ─────────────────────────────────────────────────────────────────
id llm >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -d /var/lib/llm -M llm
id jarvis >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -d /var/lib/jarvis -m jarvis
id jarvis-call >/dev/null 2>&1 || useradd -r -s /bin/sh -d /home/jarvis-call -m jarvis-call
install -d -m 755 /opt/phoenix-llm /var/lib/llm /var/lib/llm/models
install -m 755 -o root -g root "$ENGINE" /opt/phoenix-llm/llama-server        # root-owned: the service can't rewrite its own code
install -m 644 -o root -g root "$MODEL" /var/lib/llm/models/llama3.2-3b-q4km.gguf

# ── 3. Keys (generated once, kept on re-run; never echoed) ──────────────────────────────────
install -d -m 750 -o root -g llm /etc/phoenix-llm
install -d -m 755 /etc/openjarvis
umask 077
[[ -s /etc/phoenix-llm/engine.key ]] || python3 -c 'import secrets;print(secrets.token_urlsafe(32))' > /etc/phoenix-llm/engine.key
[[ -s /etc/openjarvis/jarvis.key ]]  || python3 -c 'import secrets;print(secrets.token_urlsafe(32))' > /etc/openjarvis/jarvis.key
printf 'OPENJARVIS_API_KEY=%s\nLLAMACPP_API_KEY=%s\n' "$(cat /etc/openjarvis/jarvis.key)" "$(cat /etc/phoenix-llm/engine.key)" > /etc/openjarvis/api.env
install -m 640 -o root -g jarvis-call /etc/openjarvis/jarvis.key /etc/openjarvis/gate.key
umask 022
chown root:llm /etc/phoenix-llm/engine.key; chmod 640 /etc/phoenix-llm/engine.key
chown root:root /etc/openjarvis/api.env /etc/openjarvis/jarvis.key; chmod 600 /etc/openjarvis/api.env /etc/openjarvis/jarvis.key

# ── 4. OpenJarvis (root-owned code, jarvis-owned state only) ────────────────────────────────
install -d -o root -g root $O $O/src
install -d -o jarvis -g jarvis /var/lib/jarvis/.openjarvis
tar -xzf "$SRC" -C $O/src && chown -R root:root $O/src
dpkg -s python3-venv >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get -y -q install python3-venv >/dev/null
[[ -x $O/venv/bin/python ]] || python3 -m venv $O/venv
$O/venv/bin/pip install -q "$O/src[server]"
$O/venv/bin/pip freeze > $O/installed-requirements.txt          # what actually got installed, for the record
chown -R root:root $O/venv $O/src                               # Jarvis can't rewrite his own code (JARVIS-S08)
echo "deps recorded: $O/installed-requirements.txt sha256 $(sha256sum $O/installed-requirements.txt | cut -c1-16)"

install -m 644 "$HERE/jarvis_identity.md" $O/jarvis_identity.md
install -m 644 -o jarvis -g jarvis "$HERE/config.toml" /var/lib/jarvis/.openjarvis/config.toml
install -m 755 "$HERE/jarvis-gate.py" $O/jarvis-gate
install -m 644 "$HERE/phoenix-llm.service" /etc/systemd/system/phoenix-llm.service
install -m 644 "$HERE/openjarvis.service" /etc/systemd/system/openjarvis.service

install -d -m 700 -o jarvis-call -g jarvis-call /home/jarvis-call/.ssh
for PUB in "$@"; do printf 'restrict,from="10.42.0.0/16",command="%s/jarvis-gate" %s\n' $O "$(cat "$PUB")"; done > /home/jarvis-call/.ssh/authorized_keys
chown jarvis-call:jarvis-call /home/jarvis-call/.ssh/authorized_keys; chmod 600 /home/jarvis-call/.ssh/authorized_keys

# ── 5. Start and prove: engine answers only with its key, Jarvis answers only with his ──────
systemctl daemon-reload
systemctl enable phoenix-llm openjarvis >/dev/null 2>&1
systemctl restart phoenix-llm
for _ in $(seq 1 60); do curl -fs http://127.0.0.1:8080/health >/dev/null 2>&1 && break; sleep 2; done
code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/v1/models || true)
[[ "$code" == "401" ]] || { echo "engine answered /v1/models without a key (HTTP $code) - stopping"; exit 1; }
systemctl restart openjarvis
for _ in $(seq 1 60); do curl -fs http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 2; done
code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/v1/models || true)
[[ "$code" == "401" ]] || { echo "jarvis answered /v1/models without a key (HTTP $code) - stopping"; exit 1; }
echo "jarvis up on 127.0.0.1:8000 (key required), engine on 127.0.0.1:8080 (key required), no network out"
echo "web UI: put the key from /etc/openjarvis/jarvis.key into Jarvis Settings once (sudo cat it on the box)"
