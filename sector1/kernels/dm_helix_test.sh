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
RAM=${HELIX_RAM_MB:-256}
LOOPB=
if [ -n "${HELIX_STRAND_B:-}" ]; then     # double helix: Strand B on a fast device (image file)
  BIMG=${HELIX_B_IMG:-/mnt/helix/helix-strandB.img}
  [ -f "$BIMG" ] || fallocate -l 512M "$BIMG"
  LOOPB=$(sudo losetup --direct-io=on --show -f "$BIMG")
  TABLE="0 $SZ helix $LOOP $RAM $LOOPB 512"
else
  TABLE="0 $SZ helix $LOOP $RAM"
fi
sudo dmsetup create helix0 --table "$TABLE" && ok "dm target: $(sudo dmsetup status helix0 | cut -d' ' -f4) helix, ${RAM} MiB Strand A${LOOPB:+, 512 MiB Strand B on $LOOPB}" || bad "dmsetup create"
D=/dev/mapper/helix0
ONLY=${HELIX_TEST_ONLY:-}          # e.g. HELIX_TEST_ONLY=8 runs just the Dandelion step

if [ -z "$ONLY" ]; then
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
fi   # end of steps 1-7
echo "== 8. the Dandelion: heat under load, relief by zlib-5 compression, cooling with data"
st(){ sudo dmsetup status helix0 | grep -oE "heat [0-9.]+ state [a-z]+ compression [0-9.]+|zlib5 [0-9]+|cooled_bytes [0-9]+|zhits [0-9]+|zfail [0-9]+" | tr '\n' ' '; echo; }
SRC=/tmp/hx_docs.tar
sudo tar -C /usr -cf $SRC share/doc 2>/dev/null
SRCMB=$(( $(stat -c %s $SRC) / 1048576 ))
# write compressible text straight onto the device, then read it once so she holds it
sudo dd if=$SRC of=$D bs=1M oflag=direct status=none
sudo dd if=$D of=/dev/null bs=1M count=$SRCMB iflag=direct status=none
echo "  held ${SRCMB} MiB of text:  $(st)"
BW0=$(sudo dmsetup status helix0 | grep -oE "b_writes [0-9]+" | cut -d' ' -f2)
# hammer a small hot region far from the text: her heat should rise
sudo fio --name=heat --filename=$D --rw=randread --bs=4k --offset=1500m --size=16m --direct=1 \
  --runtime=30 --time_based=1 --output-format=terse >/dev/null 2>&1 &
FIO=$!
for s in 5 10 15 20 25 30; do sleep 5; echo "  t=${s}s under load: $(st)"; done
wait $FIO   # not a bare wait: that also waits on the tee process substitution forever
for s in 5 10 15; do sleep 5; echo "  t=+${s}s idle:      $(st)"; done
Z=$(sudo dmsetup status helix0 | grep -oE "zlib5 [0-9]+" | cut -d' ' -f2)
F=$(sudo dmsetup status helix0 | grep -oE "zfail [0-9]+" | cut -d' ' -f2)
BW=$(sudo dmsetup status helix0 | grep -oE "b_writes [0-9]+" | cut -d' ' -f2)
if [ -n "$LOOPB" ]; then   # double: cold blocks go to Strand B (the bigger relief), warm ones compress
  [ "$(( ${Z:-0} + ${BW:-0} - ${BW0:-0} ))" -gt 0 ] && ok "relief under load: $(( ${BW:-0} - ${BW0:-0} )) blocks to Strand B, ${Z:-0} compressed" || bad "no relief happened under load"
else
  [ "${Z:-0}" -gt 0 ] && ok "she compressed ${Z} cold blocks with zlib 5 under load" || bad "no compression happened under load"
fi
[ "${F:-1}" -eq 0 ] && ok "zero compression/decompression failures" || bad "zfail=$F"
a=$(sudo dd if=$D bs=1M count=$SRCMB iflag=direct status=none | sha256sum | cut -d' ' -f1)
b=$(head -c $((SRCMB * 1048576)) $SRC | sha256sum | cut -d' ' -f1)
[ "$a" = "$b" ] && ok "text read back through her (compressed blocks inflated) == source" || bad "DATA MISMATCH after compression"
echo "  after read-back:   $(st)"
if [ -n "$LOOPB" ]; then
echo "== 9. double helix: Strand B carried the load"
g(){ sudo dmsetup status helix0 | grep -oE "$1 [0-9]+" | head -1 | cut -d' ' -f2; }
[ "$(g b_writes)" -gt 0 ] && ok "blocks moved A -> B: $(g b_writes) (zero-copy rung drops: $(g b_zero_copy))" || bad "nothing moved to Strand B"
[ "$(g b_hits)" -gt 0 ] && ok "reads answered by Strand B: $(g b_hits)" || bad "Strand B never answered a read"
[ "$(g b_ioerr)" -eq 0 ] && ok "zero Strand B I/O errors" || bad "b_ioerr=$(g b_ioerr)"
echo "== 10. working set bigger than Strand A: 4k random reads over 200 MiB, ${RAM} MiB RAM, 30 s"
r "raw disk (no helix)" "$LOOP"
r "double pass 1 (filling A+B)" $D
r "double pass 2 (A + B serve)" $D
echo "  strands: $(sudo dmsetup status helix0 | grep -oE "strandB slots [0-9]+ used [0-9]+ bonly [0-9]+ rungs [0-9]+ b_hits [0-9]+")"
fi
echo "== dm-helix status:"; sudo dmsetup status helix0
sudo dmsetup remove helix0 && sudo rmmod helix && ok "clean teardown" || bad "teardown"
sudo losetup -d "$LOOP"
[ -n "$LOOPB" ] && sudo losetup -d "$LOOPB"
echo "== kernel log:"
if sudo dmesg | grep -iE "oops|bug:|call trace|refcount|use-after|soft lockup"; then bad "kernel problems logged"; else ok "no oops/lockups"; fi
echo "== RESULT: $fail failure(s)"
exit $fail
