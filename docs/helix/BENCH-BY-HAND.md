# Helix bench, by hand (Jerry runs it, fio reports it)

Jerry 2026-10-07: "i dont trust those numbers because we didnt do it, claude did it in his head and the
same claude ran audits... i want to myself prep helix for a bench and see." So: every command below is
typed by Jerry, and every number is printed by `fio` itself on his screen and saved to a file. Nothing
here is summarised by Claude.

**Where:** the Compaq (pbmIII). From PBMII, PS7: `ssh pbm-compaq` (or `pb3`). Everything below runs in
that SSH session. **Safety:** only image FILES are used, never a real disk device. Nothing is set
read-only. Helix is removed at the end; the images are deleted at the end.

## What makes it fair (the two traps from last time)
1. **Linux's own cache stays ON for the baseline.** Dropping it is how she "won" 4-24x before; with it on
   it was a tie. The honest question is: does she beat the standard, with the standard working properly?
2. **The data is random**, not zeros. Zeros compress to nothing and flatter her zlib tier.
3. **The working set is bigger than RAM** (the Compaq has 16 GB; the test reads from 24 GB), on the slow
   HDD, so caching actually has to choose.
4. **The access pattern is realistic:** zipf (some blocks hot, most cold), the same seed for every run.

## 0. Get ready (once)
```bash
cd /opt/phoenix/sector1/kernels
free -g ; df -h /mnt/helix-egress /        # need ~26 GB free on the HDD, ~17 GB on the SSD
mkdir -p ~/helixbench && cd ~/helixbench
B=/mnt/helix-egress/benchorigin.img        # the slow disk (Toshiba HDD)
fallocate -l 24G $B
sudo fio --name=fill --filename=$B --rw=write --bs=1M --size=24g --refill_buffers --direct=1
```
`--refill_buffers` writes fresh random data into every block (not zeros).

The test command, used for every run (same seed, 2 minutes, 4 KiB random reads, zipf hot/cold):
```bash
T="--rw=randread --bs=4k --size=24g --random_distribution=zipf:1.1 --randseed=7 --time_based --runtime=120 --ioengine=libaio --iodepth=16 --group_reporting"
```

## 1. Run A — standard Linux (its page cache ON)
```bash
L=$(sudo losetup --show -f $B)              # no direct-io: Linux caches it the normal way
sync; echo 3 | sudo tee /proc/sys/vm/drop_caches   # start cold, once
sudo fio --name=linux_pass1 --filename=$L $T --direct=0 | tee A1-linux-pass1.txt
sudo fio --name=linux_pass2 --filename=$L $T --direct=0 | tee A2-linux-pass2.txt
sudo losetup -d $L
```

## 2. Run B — Helix single (RAM only, half the RAM = 8000 MB)
```bash
cd /opt/phoenix/sector1/kernels
sudo modprobe dm_mod
sudo insmod ./helix.ko || { make && sudo insmod ./helix.ko; }   # rebuild if the kernel changed
L=$(sudo losetup --direct-io=on --show -f $B)  # direct-io under her, so Linux doesn't cache twice
SZ=$(sudo blockdev --getsz $L)
sudo dmsetup create helixbench --table "0 $SZ helix $L 8000"
cd ~/helixbench
sync; echo 3 | sudo tee /proc/sys/vm/drop_caches
sudo fio --name=helix_pass1 --filename=/dev/mapper/helixbench $T --direct=1 | tee B1-helix-pass1.txt
sudo fio --name=helix_pass2 --filename=/dev/mapper/helixbench $T --direct=1 | tee B2-helix-pass2.txt
sudo dmsetup status helixbench | tee B-helix-status.txt     # her own counters: hits, misses, tiers
sudo dmsetup remove helixbench ; sudo losetup -d $L
```

## 3. Run C — Helix double (+ Strand B on the SSD, 16 GB)
```bash
SB=~/helixbench/strandB.img ; fallocate -l 16G $SB
L=$(sudo losetup --direct-io=on --show -f $B) ; LB=$(sudo losetup --direct-io=on --show -f $SB)
SZ=$(sudo blockdev --getsz $L)
sudo dmsetup create helixbench --table "0 $SZ helix $L 8000 $LB 16000"
sync; echo 3 | sudo tee /proc/sys/vm/drop_caches
sudo fio --name=double_pass1 --filename=/dev/mapper/helixbench $T --direct=1 | tee C1-double-pass1.txt
sudo fio --name=double_pass2 --filename=/dev/mapper/helixbench $T --direct=1 | tee C2-double-pass2.txt
sudo dmsetup status helixbench | tee C-double-status.txt
sudo dmsetup remove helixbench ; sudo losetup -d $L ; sudo losetup -d $LB
```
Note: run C has an SSD helping her that run A doesn't. The fair standard for C is Linux + an SSD cache
(lvmcache/bcache) — a later run. A vs B is the clean comparison.

## 4. Read the numbers yourself
```bash
grep -H -E "read: IOPS|lat \(usec\): min|99.00th" ~/helixbench/*-pass*.txt
```
For each run: **IOPS** (higher = better), **BW** (MB/s), **avg latency** and **99th percentile** (lower =
better). Pass 1 = from cold; pass 2 = after she (or Linux) has learned the pattern. The status files show
her own hits / misses / tiers if you want to see where reads were answered.

## 5. Clean up
```bash
sudo rmmod helix
rm -f /mnt/helix-egress/benchorigin.img ~/helixbench/strandB.img   # keeps the result .txt files
```

## Not covered here (separate tests)
- **Quad vs plain:** dm-helix works on plain disk blocks and has no quad in it (checked 10/7). The quad
  speed Jerry saw was the userspace Helix (`sector1/helix/`). That A/B needs its own script.
- Linux + SSD cache (lvmcache/bcache) as the fair standard for run C.
