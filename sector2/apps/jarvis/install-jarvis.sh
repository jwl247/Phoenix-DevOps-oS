#!/usr/bin/env bash
# install-jarvis.sh — Jarvis (OpenJarvis on local Ollama) on a Phoenix Debian box, with rails.
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Run as root on the box (pbmIII), from a folder holding this sector2/apps/jarvis/ set:
#   sudo bash install-jarvis.sh <openjarvis-source.tar.gz> <caller-pubkey-file> [more caller pubkeys...]
# One key per calling box (PBMII, awslh, ...); each gets the same forced command.
# Re-runnable. Needs /usr/local/bin/ollama + ollama.service with the model pulled.
# Rails: own nologin user, localhost only, IPAddressDeny=any (no traffic out at all), no analytics,
# no skills marketplace, no tools. Callers come in ONLY through jarvis-gate (SSH forced command, mesh only).
set -euo pipefail
SRC=${1:?openjarvis source tarball}; shift; [[ $# -ge 1 ]] || { echo "need at least one caller public key file"; exit 1; }
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd); O=/opt/openjarvis

id jarvis >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -d /var/lib/jarvis -m jarvis
id jarvis-call >/dev/null 2>&1 || useradd -r -s /bin/sh -d /home/jarvis-call -m jarvis-call
install -d -o jarvis -g jarvis $O $O/src /var/lib/jarvis/.openjarvis
tar -xzf "$SRC" -C $O/src && chown -R jarvis:jarvis $O/src
dpkg -s python3-venv >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get -y -q install python3-venv >/dev/null
[[ -x $O/venv/bin/python ]] || sudo -u jarvis python3 -m venv $O/venv
sudo -u jarvis $O/venv/bin/pip install -q "$O/src[server]"

install -m 644 "$HERE/jarvis_identity.md" $O/jarvis_identity.md
install -m 644 -o jarvis -g jarvis "$HERE/config.toml" /var/lib/jarvis/.openjarvis/config.toml
install -m 755 "$HERE/jarvis-gate.py" $O/jarvis-gate
install -m 644 "$HERE/openjarvis.service" /etc/systemd/system/openjarvis.service

install -d -m 700 -o jarvis-call -g jarvis-call /home/jarvis-call/.ssh
for PUB in "$@"; do printf 'restrict,from="10.42.0.0/16",command="%s/jarvis-gate" %s\n' $O "$(cat "$PUB")"; done > /home/jarvis-call/.ssh/authorized_keys
chown jarvis-call:jarvis-call /home/jarvis-call/.ssh/authorized_keys; chmod 600 /home/jarvis-call/.ssh/authorized_keys

systemctl daemon-reload
systemctl enable openjarvis >/dev/null 2>&1; systemctl restart openjarvis
for _ in $(seq 1 60); do curl -fs http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 2; done
curl -fs http://127.0.0.1:8000/health >/dev/null 2>&1 && echo "jarvis up on 127.0.0.1:8000" || { echo "jarvis not answering: journalctl -u openjarvis -n 40"; exit 1; }
