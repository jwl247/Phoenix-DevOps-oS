#!/usr/bin/env bash
# install-security.sh — Phoenix file motion sensor on a Linux mesh box (pbmIII, awslh).
# Phoenix DevOps OS | jwl247 | GPL v3
#   sudo bash install-security.sh            # from the folder holding suits/security.py
# Runs as root (it must read /etc, /root/.ssh), every 5 min via a systemd timer.
# State + chained log: /var/lib/phoenix-security. CLI: phoenix-security status|scan|alerts|summary|verify
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
install -d -m 755 /opt/phoenix-security
install -m 644 "$HERE/suits/security.py" /opt/phoenix-security/security.py
install -d -m 700 /var/lib/phoenix-security
cat > /usr/local/bin/phoenix-security <<'W'
#!/bin/sh
SECURITY_HOME=/var/lib/phoenix-security exec python3 /opt/phoenix-security/security.py "$@"
W
chmod 755 /usr/local/bin/phoenix-security
cat > /etc/systemd/system/phoenix-security.service <<'U'
[Unit]
Description=Phoenix file motion sensor (scan)
[Service]
Type=oneshot
Environment=SECURITY_HOME=/var/lib/phoenix-security
ExecStart=/usr/bin/python3 /opt/phoenix-security/security.py scan
SuccessExitStatus=3
Nice=10
IOSchedulingClass=idle
SyslogIdentifier=phoenix-security
U
cat > /etc/systemd/system/phoenix-security.timer <<'U'
[Unit]
Description=Phoenix file motion sensor every 5 min
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true
[Install]
WantedBy=timers.target
U
systemctl daemon-reload
[[ -f /var/lib/phoenix-security/state.json ]] || /usr/local/bin/phoenix-security baseline >/dev/null
systemctl enable --now phoenix-security.timer >/dev/null 2>&1
echo "phoenix-security installed: $(/usr/local/bin/phoenix-security status | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["version"], "files:", d["last_scan"] and d["last_scan"]["files"], "chain ok:", d["chain"]["ok"])')"
