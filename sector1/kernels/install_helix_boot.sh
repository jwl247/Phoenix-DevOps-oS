#!/usr/bin/env bash
# install_helix_boot.sh — make Helix + her paging manager start at boot.
# Run as root on a Linux box where the repo lives at /opt/phoenix.
# Idempotent: re-running updates the units, never touches /etc/default/helix
# once it exists, never formats a disk. No /etc/udev or /etc/modprobe.d
# changes (CLAUDE.md AI SAFETY RULES): modules load from helix.service.
set -euo pipefail
R=/opt/phoenix
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
[ -f "$R/sector1/kernels/helix_boot.sh" ] || { echo "repo not at $R"; exit 1; }

DEBIAN_FRONTEND=noninteractive apt-get install -y -qq linux-headers-amd64 build-essential fio >/dev/null
make -C "$R/sector1/kernels" >/dev/null
make -C "$R/sector1/kernels" helix_test >/dev/null
( cd "$R/sector1/kernels/libhelix" && cc -O2 -Wall -Wextra -fPIC -shared -o libhelix.so libhelix.c )
chmod 755 "$R/sector1/kernels/helix_boot.sh"

# HELIX_PROFILE=drive: Helix in front of a disk handed to a VM, exported as a
# block device (LIO iSCSI) and never mounted here (docs/plans/helix-drive-plan.md).
# Default profile: her origin partition, Strand B image, mounted at /srv/helix.
if [ ! -f /etc/default/helix ]; then
  if [ "${HELIX_PROFILE:-}" = drive ]; then
    cat > /etc/default/helix <<'EOF'
# Helix boot settings (read by /opt/phoenix/sector1/kernels/helix_boot.sh) — drive profile
HELIX_ORIGIN=/dev/vdb        # the disk she is pointed at (first extra virtio disk)
HELIX_RAM=8192               # Strand A MiB; "auto" would be half of a VM's RAM, not 8 GB
HELIX_B_DEV=/dev/vdc         # Strand B: the NVMe-backed second virtio disk, whole device
HELIX_B_MB=auto
HELIX_MOUNT=none             # exported over iSCSI; the filesystem belongs to the initiator
EOF
  else
    cat > /etc/default/helix <<'EOF'
# Helix boot settings (read by /opt/phoenix/sector1/kernels/helix_boot.sh)
HELIX_ORIGIN=/dev/disk/by-partlabel/helix-origin
HELIX_RAM=auto                        # her real size: half the machine's RAM
HELIX_B_IMG=/var/lib/helix/strandB.img  # on the fastest disk (SSD)
HELIX_B_MB=65536
HELIX_MOUNT=/srv/helix
EOF
  fi
  echo "wrote /etc/default/helix (${HELIX_PROFILE:-default} profile)"
fi
mkdir -p /var/lib/helix /var/lib/phoenix-swap && chmod 700 /var/lib/helix /var/lib/phoenix-swap

install -m 644 "$R/sector3/services/helix.service" /etc/systemd/system/helix.service
systemctl daemon-reload
if [ "${HELIX_PROFILE:-}" = drive ]; then
  systemctl enable helix.service
  echo "installed + enabled: helix.service (drive profile: no paging manager in the VM)"
else
  install -m 644 "$R/sector3/services/phoenix-paging.service" /etc/systemd/system/phoenix-paging.service
  systemctl daemon-reload
  systemctl enable helix.service phoenix-paging.service
  echo "installed + enabled: helix.service, phoenix-paging.service"
  echo "next: systemctl start helix; if /dev/mapper/helix has no filesystem yet, make one once by hand"
fi
