#!/usr/bin/env bash
# helix-pair-up.sh — turn a box's single Helix into an ingress/egress pair:
# helix@ingress over the existing origin disk, helix@egress over a second,
# blank disk. Step 3 of "Phoenix from the cloud, a worker on the ground"
# (docs/plans/compaq-road-test-plan.md, Phase 2). Run as root on the box.
#
#   helix-pair-up.sh <ingress-serial> <egress-serial>          do it
#   helix-pair-up.sh <ingress-serial> <egress-serial> check    report only
#
# Disks are named by SERIAL, never by /dev/sdX (letters move between boots).
# Guards, all checked before anything changes:
#   - ingress disk must already carry partlabel helix-origin (her origin today)
#   - egress disk is partitioned ONLY if it has no signatures at all (blank),
#     and formatted ONLY on the fresh helix-egress partition's dm device when
#     blkid finds nothing on it — never an existing filesystem
#   - no /etc/udev or /etc/modprobe.d changes (CLAUDE.md AI SAFETY RULES)
# Re-runnable: each step looks before it acts. Data on the ingress origin is
# safe throughout — dm-helix is write-through, the origin is always complete.
#
# Settings written once (never overwritten if present):
#   /etc/default/helix-ingress, /etc/default/helix-egress
#   HELIX_RAM_MB (env, default 3584) = Strand A per instance
set -euo pipefail

IN_SERIAL=${1:?usage: helix-pair-up.sh <ingress-serial> <egress-serial> [check]}
EG_SERIAL=${2:?usage: helix-pair-up.sh <ingress-serial> <egress-serial> [check]}
MODE=${3:-up}
RAM_MB=${HELIX_RAM_MB:-3584}
R=/opt/phoenix
K=$R/sector1/kernels
say() { printf '  %-9s %s\n' "$1" "$2"; }
die() { say "STOP" "$*"; exit 1; }
[ "$(id -u)" = 0 ] || die "run as root"
[ -x "$K/helix_boot.sh" ] || die "$K/helix_boot.sh missing"
grep -q 'start|stop|status \[instance\]' "$K/helix_boot.sh" || die "helix_boot.sh on this box is single-instance — update it first"
[ -f "$R/sector3/services/helix@.service" ] || die "$R/sector3/services/helix@.service missing"

disk_by_serial() { lsblk -dno NAME,SERIAL | awk -v s="$1" '$2==s {print "/dev/"$1}'; }
IN_DISK=$(disk_by_serial "$IN_SERIAL"); EG_DISK=$(disk_by_serial "$EG_SERIAL")
[ -n "$IN_DISK" ] || die "no disk with serial $IN_SERIAL"
[ -n "$EG_DISK" ] || die "no disk with serial $EG_SERIAL"
[ "$IN_DISK" != "$EG_DISK" ] || die "ingress and egress are the same disk"
ROOT_DISK=/dev/$(lsblk -no PKNAME "$(findmnt -no SOURCE /)")
[ "$EG_DISK" != "$ROOT_DISK" ] && [ "$IN_DISK" != "$ROOT_DISK" ] || die "refusing: one of them is the OS disk ($ROOT_DISK)"
echo "== helix pair ($MODE): ingress $IN_SERIAL=$IN_DISK  egress $EG_SERIAL=$EG_DISK  Strand A ${RAM_MB} MiB each"

# ── 1. ingress origin ────────────────────────────────────────────────────
IN_PART=$(lsblk -lno NAME,PARTLABEL "$IN_DISK" | awk '$2=="helix-origin"{print "/dev/"$1}')
[ -n "$IN_PART" ] || die "ingress disk has no partlabel helix-origin"
say "ingress" "origin $IN_PART (partlabel helix-origin)"

# ── 2. egress origin: partition a blank disk ─────────────────────────────
EG_PART=$(lsblk -lno NAME,PARTLABEL "$EG_DISK" | awk '$2=="helix-egress"{print "/dev/"$1}')
if [ -n "$EG_PART" ]; then say "egress" "origin $EG_PART (partlabel helix-egress)"
elif [ "$MODE" = check ]; then die "egress disk has no helix-egress partition"
else
  [ -z "$(wipefs -n "$EG_DISK" 2>/dev/null | tail -n +2)" ] || die "egress disk $EG_DISK is not blank — refusing to partition"
  [ -z "$(lsblk -lno NAME "$EG_DISK" | tail -n +2)" ] || die "egress disk $EG_DISK has partitions — refusing"
  printf 'label: gpt\n,,L\n' | sfdisk -q "$EG_DISK"
  sfdisk -q --part-label "$EG_DISK" 1 helix-egress
  partprobe "$EG_DISK" 2>/dev/null || true; udevadm settle 2>/dev/null || true; sleep 1
  EG_PART=$(lsblk -lno NAME,PARTLABEL "$EG_DISK" | awk '$2=="helix-egress"{print "/dev/"$1}')
  [ -n "$EG_PART" ] || die "partition created but partlabel helix-egress not visible"
  say "egress" "created $EG_PART (GPT, partlabel helix-egress)"
fi

# ── 3. per-instance settings (written once) ──────────────────────────────
write_conf() { # instance origin bimg bmb warm_write
  local f=/etc/default/helix-$1
  if [ -f "$f" ]; then say "config" "$f exists — left as is"; return; fi
  [ "$MODE" = check ] && die "$f missing"
  cat > "$f" <<EOF
# helix@$1 settings (read by $K/helix_boot.sh start $1)
# Written by sector3/worker-up/helix-pair-up.sh $(date -Is)
HELIX_ORIGIN=$2
HELIX_RAM=$RAM_MB                        # explicit: auto = half the RAM PER instance
HELIX_B_IMG=$3
HELIX_B_MB=$4
HELIX_MOUNT=/srv/helix-$1
HELIX_WARM_WRITE=$5                      # 1 on ingress: what comes in is warm on first use
EOF
  say "config" "wrote $f"
}
write_conf ingress /dev/disk/by-partlabel/helix-origin /var/lib/helix/strandB.img 65536 1
write_conf egress  /dev/disk/by-partlabel/helix-egress /var/lib/helix/strandB-egress.img 32768 0

# ── 4. hand over from the single helix.service ───────────────────────────
if [ "$MODE" != check ]; then
  install -m 644 "$R/sector3/services/helix@.service" /etc/systemd/system/helix@.service
  systemctl daemon-reload
  if systemctl is-active -q helix.service || dmsetup status helix >/dev/null 2>&1; then
    systemctl stop phoenix-paging.service 2>/dev/null || true
    systemctl stop helix.service
    say "single" "helix.service stopped (origin unmounted, device removed)"
  fi
  systemctl disable -q helix.service 2>/dev/null || true
  systemctl enable -q helix@ingress.service helix@egress.service
fi

# ── 5. up, and a filesystem on the NEW egress device only ────────────────
if [ "$MODE" != check ]; then
  systemctl start helix@ingress.service
  systemctl start helix@egress.service
  if ! blkid -p /dev/mapper/helix-egress >/dev/null 2>&1; then
    mkfs.ext4 -q -L helix-egress /dev/mapper/helix-egress
    say "egress" "ext4 made on /dev/mapper/helix-egress (new, blank)"
    systemctl restart helix@egress.service     # now it mounts
  fi
  systemctl start phoenix-paging.service 2>/dev/null || true
fi

# ── 6. prove it ──────────────────────────────────────────────────────────
for i in ingress egress; do
  st=$(dmsetup status "helix-$i" 2>/dev/null || true)
  echo "$st" | grep -q "helix double dandelion" || die "helix-$i not up as a double strand"
  mnt=$(findmnt -no TARGET "/dev/mapper/helix-$i" || true)
  [ -n "$mnt" ] || die "helix-$i up but not mounted"
  say "$i" "double dandelion, $(echo "$st" | grep -o 'state [a-z]*'), mounted $mnt"
done
say "paging" "$(systemctl is-active phoenix-paging.service)"
echo "== helix pair ready"
