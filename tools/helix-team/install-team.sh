#!/usr/bin/env bash
# install-team.sh — make the whole Helix team start at boot on a Debian box
# where the repo lives at /opt/phoenix. Run as root. Idempotent.
#
#   helix.service           kernel Helix (dm-helix double strand, Dandelion) + Frank3 slots
#   phoenix-paging.service  paging manager, fed by her kernel
#   helix-vram.service      memory manager (userspace double Helix) over /run/phoenix/helix-vram.sock
#   helix-guardian.service  ring guardian: config/port conflicts + heartbeat
#   translator.sh           the sector-3 boundary translator (no service: called on output only)
#
# Never runs sector3/services/install-units.sh (legacy units with dead paths).
# No /etc/udev, /etc/modprobe.d, drive or readonly changes (CLAUDE.md AI SAFETY RULES).
set -euo pipefail
R=/opt/phoenix
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
[ -f "$R/sector1/helix/helix_vramd.py" ] || { echo "repo not at $R (run tools/helix-team/deploy-compaq.sh first)"; exit 1; }

# 1. kernel Helix + paging (builds modules, writes /etc/default/helix once)
HELIX_PROFILE="${HELIX_PROFILE:-}" bash "$R/sector1/kernels/install_helix_boot.sh"

# 2. group for socket users, state dirs
getent group phoenix >/dev/null || groupadd --system phoenix
mkdir -p /var/lib/helix/vram /var/lib/phoenix/guardian
chmod 700 /var/lib/helix/vram
chmod 750 /var/lib/phoenix/guardian

# 3. settings files, written once
if [ ! -f /etc/default/helix-vram ]; then
  install -m 644 "$R/sector1/helix/helix_vramd.env" /etc/default/helix-vram
  echo "wrote /etc/default/helix-vram"
fi

# 4. units
install -m 644 "$R/sector3/services/helix-vram.service" /etc/systemd/system/helix-vram.service
install -m 644 "$R/sector3/services/helix-guardian.service" /etc/systemd/system/helix-guardian.service
chmod 755 "$R/sector1/helix/helix_vramd.py" "$R/sector4/guardian/integrated_guardian.py" "$R/sector3/translator/translator.sh"
systemctl daemon-reload
systemctl enable helix-vram.service helix-guardian.service

# 5. start what is not running (helix first; the rest follow their After=)
for u in helix phoenix-paging helix-vram helix-guardian; do
  if [ "${HELIX_PROFILE:-}" = drive ] && [ "$u" = phoenix-paging ]; then continue; fi
  systemctl is-active --quiet "$u" || systemctl start "$u" || echo "WARN: $u did not start (journalctl -u $u)"
done
echo "team installed + enabled: helix, phoenix-paging, helix-vram, helix-guardian"
echo "verify: $R/tools/helix-team/verify-team.sh"
