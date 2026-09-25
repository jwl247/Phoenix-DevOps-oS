// SPDX-License-Identifier: GPL-2.0
/*
 * dm_helix.c — Helix in the kernel (device-mapper target "helix")
 * jwl247 / Jerry Leftwich — GPL. Built into helix.ko.
 *
 * Table line:   <start> <len> helix <origin_dev> <ram_mb>
 *   dmsetup create helix0 --table "0 $(blockdev --getsz /dev/sdX) helix /dev/sdX 512"
 *
 * Every Helix has the Dandelion at her center: "they are not helix if they
 * don't have the dandelion in the middle". Only the double helix differs, by
 * one extra strand. This is the single-strand Helix, with everything else.
 * Design source: OG_double_helix_complete.py (vault) and its optimized
 * descendant CoPES src/helix.py.
 *
 *   DANDELION (center)  64 lanes out to the strand's block clusters; each lane
 *                       has its own lock and LRU, so lanes run side by side.
 *                       Heat rises under load (+load*0.1) and cools (-0.05);
 *                       compression factor = max(0.3, 1 - load*0.7) under load,
 *                       relaxing +0.1 per tick; states cold/hot/surging/cooling.
 *   STRAND A (speed)    4 KiB blocks of the origin device held in RAM.
 *   COMPRESSION         under load the Dandelion tightens the strand: the
 *                       coldest blocks are compressed in RAM with Helix's own
 *                       format (zlib, level 5), which frees memory (relief)
 *                       without dropping them. A compressed block that gets
 *                       read is inflated and promoted back.
 *   TEMPERATURE         per block, as in the OG PageMetrics: accesses in the
 *                       last 60 s -> BLAZING >10, HOT >5, WARM >2, COLD if seen
 *                       within 300 s, else FROZEN. Access intervals give a
 *                       predicted next access; a block expected back within
 *                       2 s is never compressed.
 *
 * Integrity rules (unchanged): write-through; cached copies are dropped at write
 * issue AND completion; a write generation stops a read that raced a write from
 * caching pre-write bytes. The cache is only ever a copy.
 */
#define DM_MSG_PREFIX "helix"
#include <linux/module.h>
#include <linux/device-mapper.h>
#include <linux/bio.h>
#include <linux/xarray.h>
#include <linux/highmem.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include <linux/spinlock.h>
#include <linux/percpu.h>
#include <linux/workqueue.h>
#include <linux/jiffies.h>
#include <linux/zlib.h>
#include <linux/math64.h>
#include "helix.h"

#define HX_BLOCK           4096u
#define HX_SECT_SHIFT      3            /* 8 sectors per 4 KiB block */
#define HX_LANES           64           /* OG DandelionAI num_lanes */
#define HX_CLUSTER_SHIFT   4            /* 16 neighbouring blocks share a lane */
#define HX_ZLEVEL          5            /* Helix's compression format: zlib 5 */
#define HX_Z_KEEP_MAX      3686         /* compress only if <= 90% of a block */
#define HX_TICK_MS         1000
#define HX_Z_PER_TICK      256          /* compression work cap per tick */
#define HX_PREDICT_GUARD_MS 2000        /* don't compress what's due back soon */

static unsigned int dandelion_ops_ref = 20000;
module_param(dandelion_ops_ref, uint, 0644);
MODULE_PARM_DESC(dandelion_ops_ref, "Block ops/s that count as full I/O load for the Dandelion's heat");

/* Shared with helix_kmod.c (/proc/helix, GET_STATS, Frank's slots). */
atomic_t helix_dandelion_heat = ATOMIC_INIT(0);          /* 0..1000 */
atomic_t helix_dandelion_state = ATOMIC_INIT(HX_COOL_COLD);
atomic_t helix_dandelion_compression = ATOMIC_INIT(1000); /* 300..1000 */

struct hx_entry {
	struct page *pg;            /* raw block, or NULL when compressed */
	void *z;                    /* zlib-5 block when compressed */
	u16 zlen;
	u16 win_hits;               /* accesses in the current 60 s window */
	u32 win_start;              /* seconds */
	unsigned long last;         /* jiffies of last access */
	u32 interval_ms;            /* smoothed access interval */
	unsigned long idx;
	struct list_head lru;       /* in its lane, head = coldest */
};

struct hx_lane {
	spinlock_t lock;
	struct list_head lru;
	unsigned long count;        /* entries */
	unsigned long pages;        /* raw blocks held */
	u64 zbytes;                 /* compressed bytes held */
	unsigned long zcount;       /* compressed blocks held */
};

struct hx_cache {
	struct dm_dev *dev;
	unsigned int ram_mb;
	u64 lane_budget;            /* bytes per lane */
	struct xarray blocks;       /* idx -> hx_entry; changed only under its lane lock */
	struct hx_lane lanes[HX_LANES];
	atomic64_t wgen;            /* bumped on every write issue + completion */
	atomic64_t hits, zhits, misses, inserts, evictions, invalidations, bypass;
	atomic64_t compressed, zfail, cooled_bytes;

	/* the Dandelion */
	u32 heat;                   /* 0..1000 */
	u32 compression;            /* 300..1000 */
	int state;
	u64 last_ops;
	unsigned int temps[5];      /* FROZEN..BLAZING census, refreshed each tick */
	unsigned int next_lane;     /* round-robin for compression work */
	void *deflate_ws;           /* used only by the tick (single-threaded) */
	void * __percpu *inflate_ws;/* per-CPU, used under a lane lock */
	struct delayed_work tick;
};

struct hx_pb {                    /* per-bio data */
	struct bvec_iter iter;
	sector_t rel;
	u64 gen;
	bool fill;
	bool write;
};

static inline struct hx_lane *hx_lane_of(struct hx_cache *hc, unsigned long idx)
{
	return &hc->lanes[(idx >> HX_CLUSTER_SHIFT) & (HX_LANES - 1)];
}

static inline u64 hx_lane_usage(struct hx_lane *ln)
{
	return (u64)ln->pages * HX_BLOCK + ln->zbytes;
}

/* ── temperature (OG PageMetrics) ───────────────────────────────────────── */
static void hx_touch(struct hx_entry *e)
{
	u32 now_s = (u32)(jiffies / HZ);

	if (now_s - e->win_start >= 60) {
		e->win_start = now_s;
		e->win_hits = 0;
	}
	if (e->win_hits < U16_MAX)
		e->win_hits++;
	if (e->last) {
		u32 dt = jiffies_to_msecs(jiffies - e->last);

		e->interval_ms = e->interval_ms ? (e->interval_ms * 7 + dt) / 8 : dt;
	}
	e->last = jiffies;
}

static int hx_temp(const struct hx_entry *e)
{
	u32 now_s = (u32)(jiffies / HZ);
	u32 recent = (now_s - e->win_start < 60) ? e->win_hits : 0;

	if (recent > 10)
		return HX_TEMP_BLAZING;
	if (recent > 5)
		return HX_TEMP_HOT;
	if (recent > 2)
		return HX_TEMP_WARM;
	if (time_before(jiffies, e->last + 300 * HZ))
		return HX_TEMP_COLD;
	return HX_TEMP_FROZEN;
}

/* OG PageMetrics._predict_next_access: next = last + mean interval.
 * True when that predicted access falls within the next 2 s. */
static bool hx_due_soon(const struct hx_entry *e)
{
	unsigned long predicted;

	if (!e->interval_ms)
		return false;
	predicted = e->last + msecs_to_jiffies(e->interval_ms);
	return time_after(predicted, jiffies) &&
	       time_before(predicted, jiffies + msecs_to_jiffies(HX_PREDICT_GUARD_MS));
}

/* ── entries (caller holds the lane lock) ───────────────────────────────── */
static void hx_free_entry(struct hx_lane *ln, struct hx_entry *e)
{
	list_del(&e->lru);
	if (e->pg) {
		put_page(e->pg);
		ln->pages--;
	}
	if (e->z) {
		kfree(e->z);
		ln->zbytes -= e->zlen;
		ln->zcount--;
	}
	kfree(e);
	ln->count--;
}

static void hx_evict_locked(struct hx_cache *hc, struct hx_lane *ln)
{
	while (hx_lane_usage(ln) > hc->lane_budget && !list_empty(&ln->lru)) {
		struct hx_entry *cold = list_first_entry(&ln->lru, struct hx_entry, lru);

		xa_erase(&hc->blocks, cold->idx);
		hx_free_entry(ln, cold);
		atomic64_inc(&hc->evictions);
	}
}

/* Inflate a compressed entry back into a fresh page (promotion). Lane lock
 * held, IRQs off, so the per-CPU workspace is ours. */
static bool hx_inflate_locked(struct hx_cache *hc, struct hx_lane *ln, struct hx_entry *e)
{
	struct z_stream_s s = { 0 };
	struct page *pg;
	void *dst;
	int ret;

	pg = alloc_page(GFP_ATOMIC | __GFP_NOWARN);
	if (!pg)
		return false;
	s.workspace = *this_cpu_ptr(hc->inflate_ws);
	if (zlib_inflateInit2(&s, MAX_WBITS) != Z_OK) {
		put_page(pg);
		return false;
	}
	dst = kmap_local_page(pg);
	s.next_in = e->z;
	s.avail_in = e->zlen;
	s.next_out = dst;
	s.avail_out = HX_BLOCK;
	ret = zlib_inflate(&s, Z_FINISH);
	zlib_inflateEnd(&s);
	kunmap_local(dst);
	if (ret != Z_STREAM_END || s.total_out != HX_BLOCK) {
		put_page(pg);
		atomic64_inc(&hc->zfail);
		return false;
	}
	kfree(e->z);
	ln->zbytes -= e->zlen;
	ln->zcount--;
	e->z = NULL;
	e->zlen = 0;
	e->pg = pg;
	ln->pages++;
	return true;
}

/* ── invalidation ───────────────────────────────────────────────────────── */
static void hx_invalidate(struct hx_cache *hc, sector_t rel, unsigned int sectors)
{
	unsigned long first, last, idx, flags;
	struct hx_entry *e;

	atomic64_inc(&hc->wgen);
	if (!sectors)
		return;
	first = rel >> HX_SECT_SHIFT;
	last = (rel + sectors - 1) >> HX_SECT_SHIFT;
	for (idx = first; idx <= last; idx++) {
		struct hx_lane *ln = hx_lane_of(hc, idx);

		spin_lock_irqsave(&ln->lock, flags);
		e = xa_load(&hc->blocks, idx);
		if (e) {
			xa_erase(&hc->blocks, idx);
			hx_free_entry(ln, e);
			atomic64_inc(&hc->invalidations);
		}
		spin_unlock_irqrestore(&ln->lock, flags);
		if (last - first > 4096 && !xa_find(&hc->blocks, &(unsigned long){ idx + 1 }, last, XA_PRESENT))
			break;              /* huge discard: stop once nothing remains */
	}
}

static bool hx_aligned(sector_t rel, unsigned int bytes)
{
	return bytes && !(rel & ((1 << HX_SECT_SHIFT) - 1)) && !(bytes & (HX_BLOCK - 1));
}

/* ── read hit ───────────────────────────────────────────────────────────── */
static bool hx_try_hit(struct hx_cache *hc, struct bio *bio, sector_t rel)
{
	struct bvec_iter it;
	struct bio_vec bv;
	u64 pos = 0;

	bio_for_each_segment(bv, bio, it) {
		unsigned int done = 0;

		while (done < bv.bv_len) {
			unsigned long idx = (rel >> HX_SECT_SHIFT) + (pos >> 12);
			unsigned int off = pos & (HX_BLOCK - 1);
			unsigned int n = min(bv.bv_len - done, HX_BLOCK - off);
			struct hx_lane *ln = hx_lane_of(hc, idx);
			struct hx_entry *e;
			struct page *pg;
			unsigned long flags;
			char *src, *dst;

			spin_lock_irqsave(&ln->lock, flags);
			e = xa_load(&hc->blocks, idx);
			if (!e) {
				spin_unlock_irqrestore(&ln->lock, flags);
				return false;
			}
			if (!e->pg) {                   /* compressed: promote */
				if (!hx_inflate_locked(hc, ln, e)) {
					spin_unlock_irqrestore(&ln->lock, flags);
					return false;
				}
				atomic64_inc(&hc->zhits);
			}
			pg = e->pg;
			get_page(pg);
			hx_touch(e);
			list_move_tail(&e->lru, &ln->lru);
			hx_evict_locked(hc, ln);        /* promotion grew the lane */
			spin_unlock_irqrestore(&ln->lock, flags);

			src = kmap_local_page(pg);
			dst = kmap_local_page(bv.bv_page);
			memcpy(dst + bv.bv_offset + done, src + off, n);
			kunmap_local(dst);
			kunmap_local(src);
			put_page(pg);

			done += n;
			pos += n;
		}
	}
	return true;
}

/* ── fill after a read miss ─────────────────────────────────────────────── */
static void hx_insert(struct hx_cache *hc, unsigned long idx, struct page *pg, u64 gen)
{
	struct hx_lane *ln = hx_lane_of(hc, idx);
	struct hx_entry *e, *old;
	unsigned long flags;

	e = kzalloc(sizeof(*e), GFP_ATOMIC | __GFP_NOWARN);
	if (!e) {
		put_page(pg);
		return;
	}
	e->pg = pg;
	e->idx = idx;
	e->win_start = (u32)(jiffies / HZ);

	spin_lock_irqsave(&ln->lock, flags);
	if (atomic64_read(&hc->wgen) != gen) {    /* a write raced this read */
		spin_unlock_irqrestore(&ln->lock, flags);
		put_page(pg);
		kfree(e);
		return;
	}
	old = xa_store(&hc->blocks, idx, e, GFP_ATOMIC | __GFP_NOWARN);
	if (xa_is_err(old)) {
		spin_unlock_irqrestore(&ln->lock, flags);
		put_page(pg);
		kfree(e);
		return;
	}
	if (old)
		hx_free_entry(ln, old);
	hx_touch(e);
	list_add_tail(&e->lru, &ln->lru);
	ln->count++;
	ln->pages++;
	atomic64_inc(&hc->inserts);
	hx_evict_locked(hc, ln);
	spin_unlock_irqrestore(&ln->lock, flags);
}

static void hx_fill(struct hx_cache *hc, struct bio *bio, struct hx_pb *pb)
{
	struct bvec_iter it;
	struct bio_vec bv;
	struct page *cur = NULL;
	u64 pos = 0;

	__bio_for_each_segment(bv, bio, it, pb->iter) {
		unsigned int done = 0;

		while (done < bv.bv_len) {
			unsigned long idx = (pb->rel >> HX_SECT_SHIFT) + (pos >> 12);
			unsigned int off = pos & (HX_BLOCK - 1);
			unsigned int n = min(bv.bv_len - done, HX_BLOCK - off);
			char *src, *dst;

			if (off == 0)
				cur = alloc_page(GFP_ATOMIC | __GFP_NOWARN);
			if (cur) {
				src = kmap_local_page(bv.bv_page);
				dst = kmap_local_page(cur);
				memcpy(dst + off, src + bv.bv_offset + done, n);
				kunmap_local(dst);
				kunmap_local(src);
				if (off + n == HX_BLOCK) {
					hx_insert(hc, idx, cur, pb->gen);
					cur = NULL;
				}
			}
			done += n;
			pos += n;
		}
	}
	if (cur)
		put_page(cur);
}

/* ── the Dandelion ──────────────────────────────────────────────────────── */

/* Compress one raw block with zlib 5 (tick context only). Returns length or 0. */
static unsigned int hx_deflate(struct hx_cache *hc, struct page *pg, u8 *out)
{
	struct z_stream_s s = { 0 };
	void *src;
	int ret;

	s.workspace = hc->deflate_ws;
	if (zlib_deflateInit2(&s, HX_ZLEVEL, Z_DEFLATED, MAX_WBITS, 8, Z_DEFAULT_STRATEGY) != Z_OK)
		return 0;
	src = kmap_local_page(pg);
	s.next_in = src;
	s.avail_in = HX_BLOCK;
	s.next_out = out;
	s.avail_out = HX_Z_KEEP_MAX;
	ret = zlib_deflate(&s, Z_FINISH);
	zlib_deflateEnd(&s);
	kunmap_local(src);
	return ret == Z_STREAM_END ? (unsigned int)s.total_out : 0;
}

/* Relief: tighten the strand. Compress the coldest raw blocks until only
 * `compression` (x1000) of each visited lane's blocks remain raw.
 * Returns the bytes of RAM freed: the data she cools herself with. */
static u64 hx_relieve(struct hx_cache *hc, u8 *buf)
{
	unsigned int budget = HX_Z_PER_TICK, visited;
	u64 freed = 0;

	for (visited = 0; visited < HX_LANES && budget; visited++) {
		struct hx_lane *ln = &hc->lanes[hc->next_lane];
		struct { struct hx_entry *e; struct page *pg; } pick[16];
		unsigned int npick = 0, i, keep_raw;
		struct hx_entry *e;
		unsigned long flags;

		hc->next_lane = (hc->next_lane + 1) & (HX_LANES - 1);

		spin_lock_irqsave(&ln->lock, flags);
		keep_raw = (unsigned int)((u64)ln->count * hc->compression / 1000);
		list_for_each_entry(e, &ln->lru, lru) {
			if (ln->pages <= keep_raw + npick || npick == ARRAY_SIZE(pick) || npick >= budget)
				break;
			if (!e->pg || hx_temp(e) > (hc->state == HX_COOL_SURGING ? HX_TEMP_WARM : HX_TEMP_COLD))
				continue;
			if (hx_due_soon(e))
				continue;           /* predicted back within 2 s: leave it raw */
			get_page(e->pg);
			pick[npick].e = e;
			pick[npick].pg = e->pg;
			npick++;
		}
		spin_unlock_irqrestore(&ln->lock, flags);

		for (i = 0; i < npick; i++) {
			unsigned int zlen = hx_deflate(hc, pick[i].pg, buf);
			void *z = NULL;

			if (zlen)
				z = kmalloc(zlen, GFP_KERNEL | __GFP_NOWARN);
			spin_lock_irqsave(&ln->lock, flags);
			e = xa_load(&hc->blocks, pick[i].e->idx);
			/* still the same live raw block? (invalidated/replaced -> skip) */
			if (z && e == pick[i].e && e->pg == pick[i].pg) {
				memcpy(z, buf, zlen);
				e->z = z;
				e->zlen = zlen;
				e->pg = NULL;
				ln->pages--;
				ln->zbytes += zlen;
				ln->zcount++;
				put_page(pick[i].pg);       /* the entry's reference */
				atomic64_inc(&hc->compressed);
				freed += HX_BLOCK - zlen;
				z = NULL;
			}
			spin_unlock_irqrestore(&ln->lock, flags);
			kfree(z);
			put_page(pick[i].pg);               /* ours */
			budget--;
		}
	}
	return freed;
}

static void hx_dandelion_tick(struct work_struct *w)
{
	struct hx_cache *hc = container_of(to_delayed_work(w), struct hx_cache, tick);
	u64 ops = atomic64_read(&hc->hits) + atomic64_read(&hc->misses);
	u64 dops = ops - hc->last_ops;
	u32 io_load, mem_load, load;
	unsigned int temps[5] = { 0 }, i;
	u64 freed = 0, held = 0, cool;
	u8 *buf;

	hc->last_ops = ops;
	/* ops per second as a fraction (x1000) of dandelion_ops_ref */
	io_load = (u32)min_t(u64, 1000, div64_u64(dops * 1000 * 1000,
				(u64)HX_TICK_MS * max(1u, dandelion_ops_ref)));
	mem_load = helix_mem_pressure_pct() * 10;
	load = max(io_load, mem_load);

	/* OG DoubleHelixStorageSystem.compress()/decompress(), per tick.
	 * Heat rises with load; the OG base cooling (-0.05) applies once load
	 * is gone. Her real cooling is data-driven, below. */
	if (load >= 500) {
		hc->heat = min(1000u, hc->heat + load / 10);
		hc->compression = max(300u, 1000 - load * 7 / 10);
		hc->state = load > 800 ? HX_COOL_SURGING : HX_COOL_HOT;
	} else {
		hc->heat = hc->heat > 50 ? hc->heat - 50 : 0;
		hc->compression = min(1000u, hc->compression + 100);
		hc->state = hc->compression < 1000 ? HX_COOL_COOLING : HX_COOL_COLD;
	}
	if (hc->compression < 1000) {
		buf = kmalloc(HX_Z_KEEP_MAX, GFP_KERNEL | __GFP_NOWARN);
		if (buf) {
			freed = hx_relieve(hc, buf);
			kfree(buf);
		}
	}

	/* temperature census (read-only walk, one lane lock at a time) */
	for (i = 0; i < HX_LANES; i++) {
		struct hx_lane *ln = &hc->lanes[i];
		struct hx_entry *e;
		unsigned long flags;

		spin_lock_irqsave(&ln->lock, flags);
		list_for_each_entry(e, &ln->lru, lru)
			temps[hx_temp(e)]++;
		held += hx_lane_usage(ln);
		spin_unlock_irqrestore(&ln->lock, flags);
	}
	memcpy(hc->temps, temps, sizeof(temps));

	/* "She cools herself with data": heat leaves through the data she
	 * moved this tick. Freeing 5% of what she holds cools her by 0.05. */
	if (freed) {
		cool = div64_u64(freed * 1000, max_t(u64, 1, held + freed));
		hc->heat = hc->heat > cool ? hc->heat - (u32)cool : 0;
		atomic64_add(freed, &hc->cooled_bytes);
	}
	atomic_set(&helix_dandelion_heat, hc->heat);
	atomic_set(&helix_dandelion_state, hc->state);
	atomic_set(&helix_dandelion_compression, hc->compression);

	schedule_delayed_work(&hc->tick, msecs_to_jiffies(HX_TICK_MS));
}

/* ── device-mapper plumbing ─────────────────────────────────────────────── */
static int hx_map(struct dm_target *ti, struct bio *bio)
{
	struct hx_cache *hc = ti->private;
	struct hx_pb *pb = dm_per_bio_data(bio, sizeof(struct hx_pb));
	sector_t rel = dm_target_offset(ti, bio->bi_iter.bi_sector);

	pb->fill = false;
	pb->write = false;
	pb->rel = rel;

	switch (bio_op(bio)) {
	case REQ_OP_READ:
		if (!hx_aligned(rel, bio->bi_iter.bi_size)) {
			atomic64_inc(&hc->bypass);
			break;
		}
		if (hx_try_hit(hc, bio, rel)) {
			atomic64_inc(&hc->hits);
			bio_endio(bio);
			return DM_MAPIO_SUBMITTED;
		}
		atomic64_inc(&hc->misses);
		pb->iter = bio->bi_iter;
		pb->gen = atomic64_read(&hc->wgen);
		pb->fill = true;
		break;
	case REQ_OP_WRITE:
	case REQ_OP_DISCARD:
	case REQ_OP_WRITE_ZEROES:
	case REQ_OP_SECURE_ERASE:
		pb->write = true;
		pb->iter = bio->bi_iter;
		hx_invalidate(hc, rel, bio_sectors(bio));
		break;
	default:
		break;
	}

	bio_set_dev(bio, hc->dev->bdev);
	bio->bi_iter.bi_sector = rel;
	return DM_MAPIO_REMAPPED;
}

static int hx_end_io(struct dm_target *ti, struct bio *bio, blk_status_t *error)
{
	struct hx_cache *hc = ti->private;
	struct hx_pb *pb = dm_per_bio_data(bio, sizeof(struct hx_pb));

	if (pb->write)
		hx_invalidate(hc, pb->rel, pb->iter.bi_size >> 9);
	else if (pb->fill && !*error)
		hx_fill(hc, bio, pb);
	return DM_ENDIO_DONE;
}

static void hx_free_ws(struct hx_cache *hc)
{
	int cpu;

	if (hc->inflate_ws) {
		for_each_possible_cpu(cpu)
			vfree(*per_cpu_ptr(hc->inflate_ws, cpu));
		free_percpu(hc->inflate_ws);
	}
	vfree(hc->deflate_ws);
}

static int hx_ctr(struct dm_target *ti, unsigned int argc, char **argv)
{
	struct hx_cache *hc;
	unsigned int ram_mb, i;
	int r, cpu;

	if (argc != 2) {
		ti->error = "usage: helix <origin_dev> <ram_mb>";
		return -EINVAL;
	}
	if (kstrtouint(argv[1], 10, &ram_mb) || !ram_mb || ram_mb > 65536) {
		ti->error = "ram_mb must be 1..65536";
		return -EINVAL;
	}
	hc = kzalloc(sizeof(*hc), GFP_KERNEL);
	if (!hc) {
		ti->error = "out of memory";
		return -ENOMEM;
	}
	hc->deflate_ws = vzalloc(zlib_deflate_workspacesize(MAX_WBITS, MAX_MEM_LEVEL));
	hc->inflate_ws = alloc_percpu(void *);
	if (!hc->deflate_ws || !hc->inflate_ws) {
		hx_free_ws(hc);
		kfree(hc);
		ti->error = "out of memory (zlib workspaces)";
		return -ENOMEM;
	}
	for_each_possible_cpu(cpu) {
		void *ws = vzalloc(zlib_inflate_workspacesize());

		if (!ws) {
			hx_free_ws(hc);
			kfree(hc);
			ti->error = "out of memory (inflate workspace)";
			return -ENOMEM;
		}
		*per_cpu_ptr(hc->inflate_ws, cpu) = ws;
	}
	r = dm_get_device(ti, argv[0], dm_table_get_mode(ti->table), &hc->dev);
	if (r) {
		hx_free_ws(hc);
		kfree(hc);
		ti->error = "origin device lookup failed";
		return r;
	}
	hc->ram_mb = ram_mb;
	hc->lane_budget = ((u64)ram_mb << 20) / HX_LANES;
	xa_init(&hc->blocks);
	for (i = 0; i < HX_LANES; i++) {
		spin_lock_init(&hc->lanes[i].lock);
		INIT_LIST_HEAD(&hc->lanes[i].lru);
	}
	hc->compression = 1000;
	hc->state = HX_COOL_COLD;

	ti->private = hc;
	ti->per_io_data_size = sizeof(struct hx_pb);
	ti->num_flush_bios = 1;
	ti->num_discard_bios = 1;
	ti->num_write_zeroes_bios = 1;

	INIT_DELAYED_WORK(&hc->tick, hx_dandelion_tick);
	schedule_delayed_work(&hc->tick, msecs_to_jiffies(HX_TICK_MS));
	helix_intent_post("dandelion_up %s ram_mb=%u lanes=%u", hc->dev->name, ram_mb, HX_LANES);
	return 0;
}

static void hx_dtr(struct dm_target *ti)
{
	struct hx_cache *hc = ti->private;
	struct hx_entry *e;
	unsigned long idx, flags;
	unsigned int i;

	cancel_delayed_work_sync(&hc->tick);
	for (i = 0; i < HX_LANES; i++) {
		struct hx_lane *ln = &hc->lanes[i];

		spin_lock_irqsave(&ln->lock, flags);
		while (!list_empty(&ln->lru)) {
			e = list_first_entry(&ln->lru, struct hx_entry, lru);
			xa_erase(&hc->blocks, e->idx);
			hx_free_entry(ln, e);
		}
		spin_unlock_irqrestore(&ln->lock, flags);
	}
	xa_for_each(&hc->blocks, idx, e)       /* nothing should remain */
		xa_erase(&hc->blocks, idx);
	xa_destroy(&hc->blocks);
	atomic_set(&helix_dandelion_heat, 0);
	atomic_set(&helix_dandelion_state, HX_COOL_COLD);
	atomic_set(&helix_dandelion_compression, 1000);
	helix_intent_post("dandelion_down %s", hc->dev->name);
	dm_put_device(ti, hc->dev);
	hx_free_ws(hc);
	kfree(hc);
}

static const char *const hx_state_names[] = { "cold", "warm", "hot", "surging", "cooling" };

static void hx_status(struct dm_target *ti, status_type_t type, unsigned int flags,
		      char *result, unsigned int maxlen)
{
	struct hx_cache *hc = ti->private;
	unsigned long pages = 0, zcount = 0, count = 0;
	u64 zbytes = 0;
	unsigned int sz = 0, i;

	switch (type) {
	case STATUSTYPE_INFO:
		for (i = 0; i < HX_LANES; i++) {
			count += READ_ONCE(hc->lanes[i].count);
			pages += READ_ONCE(hc->lanes[i].pages);
			zcount += READ_ONCE(hc->lanes[i].zcount);
			zbytes += READ_ONCE(hc->lanes[i].zbytes);
		}
		DMEMIT("dandelion heat %u.%03u state %s compression %u.%03u lanes %u "
		       "strandA blocks %lu raw %lu zlib5 %lu zbytes %llu "
		       "temps frozen %u cold %u warm %u hot %u blazing %u "
		       "hits %lld zhits %lld misses %lld inserts %lld evictions %lld "
		       "invalidations %lld compressed %lld cooled_bytes %lld zfail %lld bypass %lld",
		       hc->heat / 1000, hc->heat % 1000, hx_state_names[hc->state],
		       hc->compression / 1000, hc->compression % 1000, HX_LANES,
		       count, pages, zcount, zbytes,
		       hc->temps[0], hc->temps[1], hc->temps[2], hc->temps[3], hc->temps[4],
		       atomic64_read(&hc->hits), atomic64_read(&hc->zhits),
		       atomic64_read(&hc->misses), atomic64_read(&hc->inserts),
		       atomic64_read(&hc->evictions), atomic64_read(&hc->invalidations),
		       atomic64_read(&hc->compressed), atomic64_read(&hc->cooled_bytes),
		       atomic64_read(&hc->zfail),
		       atomic64_read(&hc->bypass));
		break;
	case STATUSTYPE_TABLE:
		DMEMIT("%s %u", hc->dev->name, hc->ram_mb);
		break;
	case STATUSTYPE_IMA:
		*result = '\0';
		break;
	}
}

static int hx_iterate_devices(struct dm_target *ti, iterate_devices_callout_fn fn, void *data)
{
	struct hx_cache *hc = ti->private;

	return fn(ti, hc->dev, 0, ti->len, data);
}

static struct target_type helix_target = {
	.name            = "helix",
	.version         = {2, 0, 0},
	.module          = THIS_MODULE,
	.ctr             = hx_ctr,
	.dtr             = hx_dtr,
	.map             = hx_map,
	.end_io          = hx_end_io,
	.status          = hx_status,
	.iterate_devices = hx_iterate_devices,
};

int dm_helix_init(void)
{
	return dm_register_target(&helix_target);
}

void dm_helix_exit(void)
{
	dm_unregister_target(&helix_target);
}
