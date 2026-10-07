#!/usr/bin/env bash
# hlk-up.sh — run H.L.K (sector3/hlk/hlk.py, pulled into the worker by the
# import method) as a service on this box. Step 5 of "Phoenix from the cloud,
# a worker on the ground" (docs/plans/compaq-road-test-plan.md, Phase 3).
# Run as root:
#   hlk-up.sh <user> <workdir> <egress-dir> <allow-from-mesh-ip>
#   e.g. hlk-up.sh a /srv/helix-ingress/phoenix-roadtest /srv/helix-egress/phoenix-roadtest-out 10.42.0.1
# Re-runnable. H.L.K runs as <user> (it reads Helix counters through
# `sudo -n dmsetup status`, so <user> needs that). It listens on 127.0.0.1 and
# this box's mesh address only; <allow-from> is the only remote caller.
set -euo pipefail
U=${1:?user}; WD=${2:?workdir}; EG=${3:?egress dir}; ALLOW=${4:?allow-from mesh ip}
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
PY="$WD/ops/hlk/hlk.py"
[ -f "$PY" ] || { echo "$PY missing — pull it first: intake clone hlk (worker-bootstrap.sh … hlk)"; exit 1; }
MESH=$(awk -F= '/^Address/ {gsub(/[ \t]/,"",$2); split($2,a,"/"); print a[1]}' /etc/phoenix-mesh/wg-phx.conf 2>/dev/null | grep '^10\.47\.0\.' || true)
[ -n "$MESH" ] || { echo "no mesh address on this box (/etc/phoenix-mesh/wg-phx.conf)"; exit 1; }
sudo -u "$U" sudo -n dmsetup status >/dev/null 2>&1 || { echo "$U can't run 'sudo -n dmsetup status' — H.L.K needs it to read Helix"; exit 1; }
install -d -o "$U" -g "$U" "$EG"
cat > /etc/systemd/system/phoenix-hlk.service <<UNIT
# phoenix-hlk — H.L.K on this worker box: directs ingress/egress Helix.
# Written by sector3/worker-up/hlk-up.sh $(date -Is). Code: $PY (imported from Phoenix).
[Unit]
Description=H.L.K on this worker (directs ingress + egress Helix)
After=network-online.target phoenix-meshd.service helix@ingress.service helix@egress.service
Wants=network-online.target

[Service]
User=$U
Environment=HLK_WORKDIR=$WD
Environment=HLK_EGRESS=$EG
EnvironmentFile=-/etc/default/phoenix-hlk
ExecStart=/usr/bin/python3 $PY --bind $MESH --allow-from $ALLOW
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable -q phoenix-hlk.service
systemctl restart phoenix-hlk.service
for i in $(seq 1 20); do curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8472/health 2>/dev/null | grep -q 200 && break; sleep 1; done
echo "  hlk      $(curl -s http://127.0.0.1:8472/health)  on 127.0.0.1 + $MESH:8472, caller $ALLOW"
echo "  token    ~$U/.phoenix-hlk/token (0600)"
