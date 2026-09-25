#!/usr/bin/env bash
# dm_helix_test.sh — dm-helix correctness + speed test. Linux, root via sudo.
# Runs ONLY on a disk-image file (default ~/helixdm/origin.img, 2 GiB), never on
# a real disk. Run from the directory holding helix.ko:  ./dm_helix_test.sh
# Exit code = number of failed checks (0 = all passed).
set -u
IMG=${HELIX_TEST_IMG:-$HOME/helixdm/origin.img}
LOG=${HELIX_TEST_LOG:-./dm_helix_test-$(date +%Y%m%d-%H%M%S).log}
exec > >(tee "$LOG") 2>&1
fail=0; ok(){ echo "  ok   $1"; }; bad(){ echo "  FAIL $1"; fail=$((fail+1)); }

mkdir -p "$(dirname "$IMG")"
[ -f "$IMG" ] || fallocate -l 2G "$IMG"
LOOP=$(sudo losetup --direct-io=on --show -f "$IMG")
SZ=$(sudo blockdev --getsz "$LOOP")
sudo dmesg -C
sudo modprobe dm_mod
sudo insmod ./helix.ko tick_ms=2000 || { echo "insmod failed"; sudo losetup -d "$LOOP"; exit 99; }
sudo dmsetup create helix0 --table "0 $SZ helix $LOOP 256" && ok "dm target on $LOOP (256 MiB RAM cache)" || bad "dmsetup create"
D=/dev/mapper/helix0

echo "== 1. randomized write + verify (mixed 4k-64k, direct I/O)"
sudo fio --name=wv --filename=$D --rw=randwrite --bs=4k-64k --size=512m --direct=1 \
  --verify=crc32c --do_verify=1 --verify_fatal=1 --randseed=42 --output-format=terse >/dev/null 2>&1 \
  && ok "write+verify 512 MiB" || bad "write+verify"
echo "== 2. re-verify: reads served from helix RAM"
sudo fio --name=wv --filename=$D --rw=randwrite --bs=4k-64k --size=512m --direct=1 \
  --verify=crc32c --verify_only --verify_fatal=1 --randseed=42 --output-format=terse >/dev/null 2>&1 \
  && ok "cached re-verify" || bad "cached re-verify"
echo "== 3. overwrite a cached block: read must return the new bytes"
head -c 1048576 /dev/urandom > /tmp/hx_A; head -c 1048576 /dev/urandom > /tmp/hx_B
sudo dd if=/tmp/hx_A of=$D bs=1M seek=100 oflag=direct status=none
sudo dd if=$D of=/tmp/hx_r1 bs=1M skip=100 count=1 iflag=direct status=none
sudo dd if=$D of=/tmp/hx_r1 bs=1M skip=100 count=1 iflag=direct status=none   # now cached
sudo dd if=/tmp/hx_B of=$D bs=1M seek=100 oflag=direct status=none
sudo dd if=$D of=/tmp/hx_r2 bs=1M skip=100 count=1 iflag=direct status=none
cmp -s /tmp/hx_A /tmp/hx_r1 && cmp -s /tmp/hx_B /tmp/hx_r2 && ok "no stale block after overwrite" || bad "STALE DATA after overwrite"
echo "== 4. concurrent mixed read/write, 4 jobs, verify"
sudo fio --name=mix --filename=$D --rw=randrw --rwmixread=70 --bs=4k --size=128m --numjobs=4 \
  --offset_increment=256m --direct=1 --verify=crc32c --verify_fatal=1 --output-format=terse >/dev/null 2>&1 \
  && ok "4-job concurrent randrw verify" || bad "concurrent verify"
echo "== 5. whole device through helix == raw origin (sha256)"
a=$(sudo dd if=$D bs=1M iflag=direct status=none | sha256sum | cut -d' ' -f1)
b=$(sudo dd if="$LOOP" bs=1M iflag=direct status=none | sha256sum | cut -d' ' -f1)
[ "$a" = "$b" ] && ok "whole device identical (${a:0:16})" || bad "device mismatch"
echo "== 6. ext4 on helix: files survive remount, fsck clean"
sudo mkfs.ext4 -q -F $D && sudo mkdir -p /mnt/hx && sudo mount $D /mnt/hx
sudo tar -C /usr -cf /mnt/hx/usr-share.tar share/doc 2>/dev/null
s1=$(sudo sha256sum /mnt/hx/usr-share.tar | cut -d' ' -f1)
sudo umount /mnt/hx; sudo sh -c "echo 3 > /proc/sys/vm/drop_caches"; sudo mount $D /mnt/hx
s2=$(sudo sha256sum /mnt/hx/usr-share.tar | cut -d' ' -f1)
[ "$s1" = "$s2" ] && ok "tarball checksum stable across remount" || bad "checksum changed"
sudo umount /mnt/hx; sudo e2fsck -fn $D >/dev/null 2>&1 && ok "e2fsck clean" || bad "e2fsck errors"
echo "== 7. speed: 4k random reads, 200 MiB region, direct I/O, 30 s each"
r(){ sudo fio --name=bench --filename=$2 --rw=randread --bs=4k --size=200m --direct=1 --runtime=30 --time_based=1 \
  --randrepeat=1 --output-format=json 2>/dev/null | sed -n '/^{/,$p' | python3 -c "import json,sys;j=json.load(sys.stdin)['jobs'][0]['read'];print(f'  {sys.argv[1]:<32} {j[\"iops\"]:9.0f} IOPS  lat {j[\"clat_ns\"][\"mean\"]/1e3:9.1f} us')" "$1" || bad "speed run $1"; }
r "raw disk (no helix)" "$LOOP"
r "helix pass 1 (filling)" $D
r "helix pass 2 (RAM hits)" $D
echo "== dm-helix status:"; sudo dmsetup status helix0
sudo dmsetup remove helix0 && sudo rmmod helix && ok "clean teardown" || bad "teardown"
sudo losetup -d "$LOOP"
echo "== kernel log:"
if sudo dmesg | grep -iE "oops|bug:|call trace|refcount|use-after|soft lockup"; then bad "kernel problems logged"; else ok "no oops/lockups"; fi
echo "== RESULT: $fail failure(s)"
exit $fail
