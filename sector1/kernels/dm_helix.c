// SPDX-License-Identifier: GPL-2.0
/*
 * dm_helix.c — Helix in the kernel (device-mapper target "helix")
 * jwl247 / Jerry Leftwich — GPL. Built into helix.ko.
 *
 * Table lines:
 *   <start> <len> helix <origin_dev> <ram_mb>                          single
 *   <start> <len> helix <origin_dev> <ram_mb> <strandB_dev> <b_mb>     double
 *
 * Every Helix has the Dandelion at her center: "they are not helix if they
 * don't have the dandelion in the middle". The double helix differs only by
 * the extra strand. Design source: OG_double_helix_complete.py (vault) and its
 * optimized descendant CoPES src/helix.py.
 *
 *   DANDELION (center)  64 lanes out to block clusters; each lane has its own
 *                       lock, so lanes run side by side. Heat rises under load
 *                       (+load*0.1) and falls (-0.05 once load is gone);
 *                       compression factor max(0.3, 1 - load*0.7) under load,
 *                       relaxing +0.1 per tick; states cold/hot/surging/cooling.
 *                       She cools herself with data: heat falls by the RAM her
 *                       relief frees.
 *   STRAND A (speed)    4 KiB blocks held in RAM.
 *   STRAND B (relief)   double only: 4 KiB slots on a second (fast) device.
 *                       When A needs room, or the Dandelion runs hot, A's cold
 *                       blocks move to B instead of being dropped.
 *   RUNGS               one entry per block, holding it on A, B or both. A read
 *                       is answered by whichever strand holds the block (A
 *                       first); a block on both leaves A with zero copy. A
 *                       block read from B is promoted back to A and keeps its B
 *                       copy. Only a block on neither strand goes to the origin.
 *   COMPRESSION         cold blocks compressed in RAM with Helix's format
 *                       (zlib level 5), inflated and promoted when read.
 *   TEMPERATURE         OG PageMetrics: accesses in the last 60 s -> BLAZING >10,
 *                       HOT >5, WARM >2, COLD if seen within 300 s, else FROZEN.
 *                       Access intervals predict the next access; a block due
 *                       back within 2 s is left in raw RAM.
 *
 * Integrity: write-through to the origin; every strand's copy of a written
 * block is dropped at write issue AND completion; a write generation stops a
 * read that raced a write from caching pre-write bytes; a B slot is never
 * reused while a read of it is in flight; a unique version on every entry change
 * stops the B writer from committing a block that changed underneath it. Both
 * strands are only ever copies: removing the target loses nothing.
 */
#define DM_MSG_PREFIX "helix"
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/device-mapper.h>
#include <linux/bio.h>
#include <linux/blkdev.h>
#include <linux/xarray.h>
#include <linux/highmem.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include <linux/spinlock.h>
#include <linux/percpu.h>
#include <linux/workqueue.h>
#include <linux/jiffies.h>
#include <linux/bitmap.h>
#include <linux/zlib.h>
#include <linux/math64.h>
#include "helix.h"

#define HX_BLOCK            4096u
#define HX_SECT_SHIFT       3            /* 8 sectors per 4 KiB block */
#define HX_LANES            64           /* OG DandelionAI num_lanes */
#define HX_CLUSTER_SHIFT    4            /* 16 neighbouring blocks share a lane */
#define HX_ZLEVEL           5            /* Helix's compression format: zlib 5 */
#define HX_Z_KEEP_MAX       3686         /* compress only if <= 90% of a block */
#define HX_TICK_MS          1000
#define HX_Z_PER_TICK       256          /* relief work cap per tick */
#define HX_PREDICT_GUARD_MS 2000         /* don't relieve what's due back soon */
#define HX_B_WRITE_BATCH    64           /* B writer: blocks per lane per pass */
#define HX_READ_WORKERS     8            /* parallel Strand B / slow-path readers */
#define HX_PEAK_FLOOR       200          /* ops/s: never calibrate below this */
#define HX_MISS_RING        4096         /* recent misses her paging manager reads (power of 2) */

static unsigned int dandelion_ops_ref;     /* 0 = she calibrates herself */
module_param(dandelion_ops_ref, uint, 0644);
MODULE_PARM_DESC(dandelion_ops_ref, "Fixed ops/s that count as full load; 0 (default) = the Dandelion calibrates to her own peak on this machine");

/* Governor tuning knob. Relief = the tick's compression and Strand B moves.
 * Default on (her normal behaviour). Off isolates the relief cost when tuning
 * her to a machine; writable at runtime: /sys/module/helix/parameters/relief_enabled */
static bool relief_enabled = true;
module_param(relief_enabled, bool, 0644);
MODULE_PARM_DESC(relief_enabled, "1 (default) = the governor relieves memory (compress / move to Strand B) under load; 0 = never (tuning)");

/* Shared with helix_kmod.c (/proc/helix, GET_STATS, Frank's slots). */
atomic_t helix_dandelion_heat = ATOMIC_INIT(0);          /* 0..1000 */
atomic_t helix_dandelion_state = ATOMIC_INIT(HX_COOL_COLD);
atomic_t helix_dandelion_compression = ATOMIC_INIT(1000); /* 300..1000 */

/* Every live instance (helix, or helix-ingress + helix-egress, ...). The three
 * atomics above are ONE published Dandelion for /proc/helix and GET_STATS, so
 * they carry the aggregate: the hottest heat, the hottest state by heat rank
 * (cold < cooling < warm < hot < surging — NOT the HX_COOL_* enum order, which
 * is a name-lookup order with cooling last), and the deepest compression.
 * Before 2026-09-29 every instance's tick overwrote them and any instance's
 * removal zeroed them, so with two instances the published Dandelion flipped
 * between them and read cold while one was still running. Each instance's own
 * Dandelion is in its `dmsetup status` line. */
static LIST_HEAD(hx_instances);
static DEFINE_MUTEX(hx_instances_lock);
static const u8 hx_heat_rank[] = {
	[HX_COOL_COLD] = 0, [HX_COOL_COOLING] = 1, [HX_COOL_WARM] = 2,
	[HX_COOL_HOT] = 3, [HX_COOL_SURGING] = 4,
};

enum hx_list { HX_ON_A, HX_ON_PEND, HX_ON_B };

struct hx_entry {
	struct page *pg;            /* raw block on A, or NULL */
	void *z;                    /* zlib-5 block on A, or NULL */
	u16 zlen;
	u16 win_hits;               /* accesses in the current 60 s window */
	u32 win_start;              /* seconds */
	unsigned long last;         /* jiffies of last access */
	u32 interval_ms;            /* smoothed access interval */
	u32 bslot;                  /* Strand B slot + 1, 0 = not on B */
	u16 b_readers;              /* in-flight reads of the B slot */
	u8 where;                   /* enum hx_list */
	u8 dead;                    /* freed while B readers were in flight */
	u64 ver;                    /* unique per change (hc->vgen) */
	unsigned long idx;
	struct list_head lru;       /* in the list named by `where` */
};

struct hx_lane {
	spinlock_t lock;
	struct list_head lru;       /* on A (raw or zlib), head = coldest */
	struct list_head pend;      /* on A, queued for the move to B */
	struct list_head blru;      /* on B only, head = oldest */
	unsigned long count;        /* entries */
	unsigned long pages;        /* raw blocks on A */
	u64 zbytes;                 /* compressed bytes on A */
	unsigned long zcount;
	u64 pend_bytes;             /* A bytes queued for B */
	unsigned long bcount;       /* entries on B only */
};

struct hx_cache {
	struct list_head node;      /* on hx_instances */
	struct dm_dev *dev;
	unsigned int ram_mb;
	u64 lane_budget;            /* A bytes per lane */
	struct xarray blocks;       /* idx -> hx_entry; changed only under its lane lock */
	struct hx_lane lanes[HX_LANES];
	atomic64_t wgen;            /* bumped on every write issue + completion */
	atomic64_t vgen;            /* entry versions */
	atomic64_t hits, zhits, misses, inserts, evictions, invalidations, bypass;
	/* What she was asked for and didn't have: her paging manager reads this to
	 * predict what's next. Lock-free ring; entry = (blocks << 48) | first block. */
	u64 *miss_ring;
	struct page **warm_pgs;      /* HX_WARM_BATCH pages for one batched warm read */
	bool warm_stopping;          /* teardown: drop the warm queue, don't drain it */
	atomic64_t miss_seq;
	atomic64_t compressed, zfail, cooled_bytes;

	/* Strand B (double only) */
	struct dm_dev *bdev;
	unsigned int b_mb;
	unsigned long b_slots;      /* Strand B working budget (her paging manager may move it) */
	unsigned long b_cap_slots;  /* the whole Strand B device: the most a Doppelganger can grow her to */
	unsigned long *b_map;
	unsigned long b_hint, b_used;
	spinlock_t b_lock;          /* nests inside a lane lock; irqsave outside one */
	unsigned int b_scan_lane;
	atomic64_t b_hits, b_writes, b_evictions, b_zero_copy, b_ioerr, b_freed;
	struct workqueue_struct *wq;
	struct work_struct b_write_work;
	struct hx_reader {
		struct work_struct work;
		struct hx_cache *hc;
	} readers[HX_READ_WORKERS];
	unsigned int next_reader;
	spinlock_t defer_lock;
	struct bio_list deferred;
	void *worker_inflate_ws;    /* for the B writer (process context) */

	/* the Dandelion */
	u32 heat;
	u32 compression;
	int state;
	u64 last_ops;
	u64 peak_ops;               /* self-calibration: busiest tick seen (decays) */
	unsigned int temps[5];
	unsigned long rungs;        /* entries on A and B at once (last census) */
	unsigned int next_lane;
	void *deflate_ws;           /* tick only */
	void * __percpu *inflate_ws;/* per-CPU, used under a lane lock */
	struct delayed_work tick;
	/* warm_write (table keyword): blocks written through her are read back
	 * into Strand A by a worker, through hx_insert's normal race guard, so
	 * data that came IN through this instance is warm on first use (ingress:
	 * "what she has read in, she knows"). Off unless asked for. */
	bool warm_write;
	spinlock_t warm_lock;
	struct list_head warm_q;             /* hx_warm ranges waiting */
	unsigned long warm_pending;          /* blocks queued */
	struct delayed_work warm_work;
	atomic64_t warmed, warm_dropped;
};

struct hx_pb {
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

static inline u64 hx_a_bytes(const struct hx_entry *e)
{
	return e->pg ? HX_BLOCK : (e->z ? e->zlen : 0);
}

/* A usage that still counts against the lane budget (queued moves excluded). */
static inline u64 hx_lane_usage(struct hx_lane *ln)
{
	u64 u = (u64)ln->pages * HX_BLOCK + ln->zbytes;

	return u > ln->pend_bytes ? u - ln->pend_bytes : 0;
}

static inline void hx_newver(struct hx_cache *hc, struct hx_entry *e)
{
	e->ver = atomic64_inc_return(&hc->vgen);
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

/* OG PageMetrics._predict_next_access: next = last + mean interval. */
static bool hx_due_soon(const struct hx_entry *e)
{
	unsigned long predicted;

	if (!e->interval_ms)
		return false;
	predicted = e->last + msecs_to_jiffies(e->interval_ms);
	return time_after(predicted, jiffies) &&
	       time_before(predicted, jiffies + msecs_to_jiffies(HX_PREDICT_GUARD_MS));
}

/* ── Strand B slots ─────────────────────────────────────────────────────── */
/* Caller holds a lane lock (IRQs already off). */
static void hx_b_free_slot_locked(struct hx_cache *hc, u32 bslot)
{
	spin_lock(&hc->b_lock);
	if (test_and_clear_bit(bslot - 1, hc->b_map))
		hc->b_used--;
	spin_unlock(&hc->b_lock);
}

/* ── entries (caller holds the lane lock) ───────────────────────────────── */
static void hx_drop_a(struct hx_lane *ln, struct hx_entry *e)
{
	if (e->pg) {
		put_page(e->pg);
		e->pg = NULL;
		ln->pages--;
	}
	if (e->z) {
		kfree(e->z);
		ln->zbytes -= e->zlen;
		ln->zcount--;
		e->z = NULL;
		e->zlen = 0;
	}
}

static void hx_set_list(struct hx_lane *ln, struct hx_entry *e, enum hx_list to)
{
	if (e->where == HX_ON_PEND)
		ln->pend_bytes -= hx_a_bytes(e);
	if (e->where == HX_ON_B)
		ln->bcount--;
	list_del(&e->lru);
	e->where = to;
	if (to == HX_ON_A)
		list_add_tail(&e->lru, &ln->lru);
	else if (to == HX_ON_PEND) {
		list_add_tail(&e->lru, &ln->pend);
		ln->pend_bytes += hx_a_bytes(e);
	} else {
		list_add_tail(&e->lru, &ln->blru);
		ln->bcount++;
	}
}

/* Remove an entry from its lane entirely (xarray already erased by caller). */
static void hx_free_entry(struct hx_cache *hc, struct hx_lane *ln, struct hx_entry *e)
{
	if (e->where == HX_ON_PEND)
		ln->pend_bytes -= hx_a_bytes(e);
	if (e->where == HX_ON_B)
		ln->bcount--;
	list_del_init(&e->lru);
	hx_drop_a(ln, e);
	ln->count--;
	if (e->bslot) {
		if (e->b_readers) {         /* a B read is in flight: it frees later */
			e->dead = 1;
			return;
		}
		hx_b_free_slot_locked(hc, e->bslot);
	}
	kfree(e);
}

/* Make room on Strand A. Single: drop the coldest. Double: the coldest goes
 * to B (zero copy when it's already there). */
static void hx_evict_locked(struct hx_cache *hc, struct hx_lane *ln, bool *kick)
{
	while (hx_lane_usage(ln) > hc->lane_budget && !list_empty(&ln->lru)) {
		struct hx_entry *cold = list_first_entry(&ln->lru, struct hx_entry, lru);

		if (hc->bdev && cold->bslot) {                  /* rung: zero copy */
			u64 b = hx_a_bytes(cold);

			hx_drop_a(ln, cold);
			hx_newver(hc, cold);
			hx_set_list(ln, cold, HX_ON_B);
			atomic64_inc(&hc->b_zero_copy);
			atomic64_add(b, &hc->b_freed);
		} else if (hc->bdev && ln->pend_bytes < hc->lane_budget) {
			hx_set_list(ln, cold, HX_ON_PEND);      /* B writer takes it */
			*kick = true;
		} else {
			xa_erase(&hc->blocks, cold->idx);
			hx_free_entry(hc, ln, cold);
			atomic64_inc(&hc->evictions);
		}
	}
}

static void hx_kick_writer(struct hx_cache *hc, bool kick)
{
	if (kick && hc->wq)
		queue_work(hc->wq, &hc->b_write_work);
}

/* Inflate a compressed A entry into a fresh page (promotion). Lane lock held. */
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
	if (e->where == HX_ON_PEND)
		ln->pend_bytes += HX_BLOCK - e->zlen;
	kfree(e->z);
	ln->zbytes -= e->zlen;
	ln->zcount--;
	e->z = NULL;
	e->zlen = 0;
	e->pg = pg;
	ln->pages++;
	hx_newver(hc, e);
	return true;
}

/* An A hit: count it, keep it on A (cancelling a queued move to B). */
static void hx_a_hit_locked(struct hx_cache *hc, struct hx_lane *ln, struct hx_entry *e)
{
	hx_touch(e);
	if (e->where == HX_ON_PEND)
		hx_newver(hc, e);           /* the B writer must not commit it now */
	hx_set_list(ln, e, HX_ON_A);
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
			hx_free_entry(hc, ln, e);
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

/* ── read, fast path (map context): everything on A ─────────────────────── */
enum hx_hit { HX_HIT, HX_MISS, HX_NEED_B };

static enum hx_hit hx_try_hit(struct hx_cache *hc, struct bio *bio, sector_t rel)
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
			bool kick = false;
			char *src, *dst;

			spin_lock_irqsave(&ln->lock, flags);
			e = xa_load(&hc->blocks, idx);
			if (!e) {
				spin_unlock_irqrestore(&ln->lock, flags);
				return HX_MISS;
			}
			if (!e->pg && !e->z) {          /* on B only: needs the worker */
				spin_unlock_irqrestore(&ln->lock, flags);
				return HX_NEED_B;
			}
			if (!e->pg) {
				if (!hx_inflate_locked(hc, ln, e)) {
					spin_unlock_irqrestore(&ln->lock, flags);
					return HX_MISS;
				}
				atomic64_inc(&hc->zhits);
			}
			pg = e->pg;
			get_page(pg);
			hx_a_hit_locked(hc, ln, e);
			hx_evict_locked(hc, ln, &kick);
			spin_unlock_irqrestore(&ln->lock, flags);
			hx_kick_writer(hc, kick);

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
	return HX_HIT;
}

/* ── fill after a read miss ─────────────────────────────────────────────── */
static void hx_insert(struct hx_cache *hc, unsigned long idx, struct page *pg, u64 gen)
{
	struct hx_lane *ln = hx_lane_of(hc, idx);
	struct hx_entry *e, *old;
	unsigned long flags;
	bool kick = false;

	e = kzalloc(sizeof(*e), GFP_ATOMIC | __GFP_NOWARN);
	if (!e) {
		put_page(pg);
		return;
	}
	e->pg = pg;
	e->idx = idx;
	e->where = HX_ON_A;
	e->win_start = (u32)(jiffies / HZ);
	INIT_LIST_HEAD(&e->lru);

	spin_lock_irqsave(&ln->lock, flags);
	if (atomic64_read(&hc->wgen) != gen) {    /* a write raced this read */
		spin_unlock_irqrestore(&ln->lock, flags);
		put_page(pg);
		kfree(e);
		return;
	}
	old = xa_load(&hc->blocks, idx);
	if (old) {                                /* someone filled it first */
		spin_unlock_irqrestore(&ln->lock, flags);
		put_page(pg);
		kfree(e);
		return;
	}
	if (xa_is_err(xa_store(&hc->blocks, idx, e, GFP_ATOMIC | __GFP_NOWARN))) {
		spin_unlock_irqrestore(&ln->lock, flags);
		put_page(pg);
		kfree(e);
		return;
	}
	hx_newver(hc, e);
	hx_touch(e);
	list_add_tail(&e->lru, &ln->lru);
	ln->count++;
	ln->pages++;
	atomic64_inc(&hc->inserts);
	hx_evict_locked(hc, ln, &kick);
	spin_unlock_irqrestore(&ln->lock, flags);
	hx_kick_writer(hc, kick);
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

/* ── synchronous block I/O for the workers (process context) ────────────── */
static int hx_sync_io(struct block_device *bdev, blk_opf_t op, sector_t sector,
		      struct page *pg)
{
	struct bio *bio = bio_alloc(bdev, 1, op, GFP_NOIO);
	int ret;

	bio->bi_iter.bi_sector = sector;
	__bio_add_page(bio, pg, HX_BLOCK, 0);
	ret = submit_bio_wait(bio);
	bio_put(bio);
	return ret;
}

/* One origin trip for n contiguous blocks — feeding her through a pipe, not a straw.
 * With a far origin every trip costs a round-trip; one block per trip capped prefetch
 * at ~400 KiB/s at 10 ms. */
static int hx_sync_read_batch(struct block_device *bdev, sector_t sector,
			      struct page **pgs, unsigned int n)
{
	struct bio *bio = bio_alloc(bdev, n, REQ_OP_READ, GFP_NOIO);
	unsigned int i;
	int ret;

	bio->bi_iter.bi_sector = sector;
	for (i = 0; i < n; i++)
		__bio_add_page(bio, pgs[i], HX_BLOCK, 0);
	ret = submit_bio_wait(bio);
	bio_put(bio);
	return ret;
}

static inline void hx_note_miss(struct hx_cache *hc, unsigned long idx, unsigned int n)
{
	u64 s;

	if (!hc->miss_ring)
		return;
	s = atomic64_inc_return(&hc->miss_seq) - 1;
	WRITE_ONCE(hc->miss_ring[s & (HX_MISS_RING - 1)],
		   ((u64)min_t(unsigned int, n, 0xffff) << 48) | ((u64)idx & ((1ULL << 48) - 1)));
}

/* ── Strand B: slot allocation (process context, no lane lock held) ─────── */
static long hx_b_alloc(struct hx_cache *hc)
{
	unsigned long flags, slot;
	int tries;

	for (tries = 0; tries < HX_LANES * 2; tries++) {
		struct hx_lane *ln;
		struct hx_entry *old;

		spin_lock_irqsave(&hc->b_lock, flags);
		slot = find_next_zero_bit(hc->b_map, hc->b_slots, hc->b_hint);
		if (slot >= hc->b_slots)
			slot = find_first_zero_bit(hc->b_map, hc->b_slots);
		if (slot < hc->b_slots) {
			set_bit(slot, hc->b_map);
			hc->b_used++;
			hc->b_hint = slot + 1;
			spin_unlock_irqrestore(&hc->b_lock, flags);
			return slot;
		}
		spin_unlock_irqrestore(&hc->b_lock, flags);

		/* B is full: B's own relief, retire its oldest B-only block */
		ln = &hc->lanes[hc->b_scan_lane];
		hc->b_scan_lane = (hc->b_scan_lane + 1) & (HX_LANES - 1);
		spin_lock_irqsave(&ln->lock, flags);
		list_for_each_entry(old, &ln->blru, lru) {
			if (old->b_readers)
				continue;
			xa_erase(&hc->blocks, old->idx);
			hx_free_entry(hc, ln, old);
			atomic64_inc(&hc->b_evictions);
			break;
		}
		spin_unlock_irqrestore(&ln->lock, flags);
	}
	return -ENOSPC;
}

/* Move queued blocks from A to B. */
static void hx_b_writer(struct work_struct *w)
{
	struct hx_cache *hc = container_of(w, struct hx_cache, b_write_work);
	struct page *tmp = alloc_page(GFP_NOIO);
	u8 *zbuf = kmalloc(HX_BLOCK, GFP_NOIO);
	unsigned int i, n;

	if (!tmp || !zbuf)
		goto out;
	for (i = 0; i < HX_LANES; i++) {
		struct hx_lane *ln = &hc->lanes[i];

		for (n = 0; n < HX_B_WRITE_BATCH; n++) {
			struct hx_entry *e;
			struct page *src = NULL;
			unsigned long flags, idx;
			unsigned int zlen = 0;
			u64 ver, moved;
			long slot;

			spin_lock_irqsave(&ln->lock, flags);
			if (list_empty(&ln->pend)) {
				spin_unlock_irqrestore(&ln->lock, flags);
				break;
			}
			e = list_first_entry(&ln->pend, struct hx_entry, lru);
			idx = e->idx;
			ver = e->ver;
			if (e->pg) {
				src = e->pg;
				get_page(src);
			} else if (e->z) {
				zlen = e->zlen;
				memcpy(zbuf, e->z, zlen);
			}
			/* rotate so a stuck entry can't starve the lane */
			list_move_tail(&e->lru, &ln->pend);
			spin_unlock_irqrestore(&ln->lock, flags);

			if (!src) {                       /* inflate the zlib block */
				struct z_stream_s s = { .workspace = hc->worker_inflate_ws };
				void *dst;
				int ret = Z_DATA_ERROR;

				if (!zlen || zlib_inflateInit2(&s, MAX_WBITS) != Z_OK)
					continue;
				dst = kmap_local_page(tmp);
				s.next_in = zbuf;
				s.avail_in = zlen;
				s.next_out = dst;
				s.avail_out = HX_BLOCK;
				ret = zlib_inflate(&s, Z_FINISH);
				zlib_inflateEnd(&s);
				kunmap_local(dst);
				if (ret != Z_STREAM_END) {
					atomic64_inc(&hc->zfail);
					continue;
				}
			}

			slot = hx_b_alloc(hc);
			if (slot < 0 || hx_sync_io(hc->bdev->bdev, REQ_OP_WRITE,
						   (sector_t)slot << HX_SECT_SHIFT, src ? src : tmp)) {
				if (slot >= 0) {
					atomic64_inc(&hc->b_ioerr);
					spin_lock_irqsave(&hc->b_lock, flags);
					if (test_and_clear_bit(slot, hc->b_map))
						hc->b_used--;
					spin_unlock_irqrestore(&hc->b_lock, flags);
				}
				/* B unavailable: drop the block from A as a plain eviction */
				spin_lock_irqsave(&ln->lock, flags);
				e = xa_load(&hc->blocks, idx);
				if (e && e->ver == ver && e->where == HX_ON_PEND) {
					xa_erase(&hc->blocks, idx);
					hx_free_entry(hc, ln, e);
					atomic64_inc(&hc->evictions);
				}
				spin_unlock_irqrestore(&ln->lock, flags);
				if (src)
					put_page(src);
				continue;
			}

			spin_lock_irqsave(&ln->lock, flags);
			e = xa_load(&hc->blocks, idx);
			if (e && e->ver == ver && e->where == HX_ON_PEND && !e->bslot) {
				moved = hx_a_bytes(e);
				e->bslot = (u32)slot + 1;
				hx_set_list(ln, e, HX_ON_B);    /* pend accounting first */
				hx_drop_a(ln, e);
				hx_newver(hc, e);
				atomic64_inc(&hc->b_writes);
				atomic64_add(moved, &hc->b_freed);
			} else {                            /* changed underneath: undo */
				hx_b_free_slot_locked(hc, (u32)slot + 1);
			}
			spin_unlock_irqrestore(&ln->lock, flags);
			if (src)
				put_page(src);
		}
	}
out:
	if (tmp)
		put_page(tmp);
	kfree(zbuf);
}

/* ── read, slow path (worker): some block lives only on Strand B ────────── */
static int hx_block_for_read(struct hx_cache *hc, unsigned long idx, u8 *out)
{
	struct hx_lane *ln = hx_lane_of(hc, idx);
	struct hx_entry *e;
	struct page *pg;
	unsigned long flags;
	bool kick = false;
	u64 ver, gen;
	u32 slot;
	void *p;

	spin_lock_irqsave(&ln->lock, flags);
	e = xa_load(&hc->blocks, idx);
	if (e && e->z && !e->pg && !hx_inflate_locked(hc, ln, e))
		e = NULL;                               /* fall through to origin */
	if (e && e->pg) {                               /* on A */
		p = kmap_local_page(e->pg);
		memcpy(out, p, HX_BLOCK);
		kunmap_local(p);
		hx_a_hit_locked(hc, ln, e);
		hx_evict_locked(hc, ln, &kick);
		spin_unlock_irqrestore(&ln->lock, flags);
		hx_kick_writer(hc, kick);
		atomic64_inc(&hc->hits);
		return 0;
	}
	if (e && e->bslot) {                            /* on B only */
		slot = e->bslot - 1;
		ver = e->ver;
		e->b_readers++;
		spin_unlock_irqrestore(&ln->lock, flags);

		pg = alloc_page(GFP_NOIO);
		if (pg && !hx_sync_io(hc->bdev->bdev, REQ_OP_READ,
				      (sector_t)slot << HX_SECT_SHIFT, pg)) {
			p = kmap_local_page(pg);
			memcpy(out, p, HX_BLOCK);
			kunmap_local(p);
		} else {
			if (pg)
				put_page(pg);
			pg = NULL;
			atomic64_inc(&hc->b_ioerr);
		}

		spin_lock_irqsave(&ln->lock, flags);
		e->b_readers--;
		if (e->dead) {                          /* freed while we read */
			if (!e->b_readers) {
				hx_b_free_slot_locked(hc, e->bslot);
				kfree(e);
			}
		} else if (pg && e->ver == ver && !e->pg && !e->z) {
			get_page(pg);                   /* promote: now on both strands */
			e->pg = pg;
			ln->pages++;
			hx_newver(hc, e);
			hx_touch(e);
			hx_set_list(ln, e, HX_ON_A);
			hx_evict_locked(hc, ln, &kick);
		}
		spin_unlock_irqrestore(&ln->lock, flags);
		hx_kick_writer(hc, kick);
		if (pg) {
			put_page(pg);
			atomic64_inc(&hc->b_hits);
			return 0;
		}
		/* B read failed: fall back to the origin */
	} else {
		spin_unlock_irqrestore(&ln->lock, flags);
	}

	/* on neither strand: read the origin and fill Strand A */
	gen = atomic64_read(&hc->wgen);
	pg = alloc_page(GFP_NOIO);
	if (!pg)
		return -ENOMEM;
	if (hx_sync_io(hc->dev->bdev, REQ_OP_READ, (sector_t)idx << HX_SECT_SHIFT, pg)) {
		put_page(pg);
		return -EIO;
	}
	p = kmap_local_page(pg);
	memcpy(out, p, HX_BLOCK);
	kunmap_local(p);
	atomic64_inc(&hc->misses);
	hx_note_miss(hc, idx, 1);
	hx_insert(hc, idx, pg, gen);                    /* takes our reference */
	return 0;
}

static void hx_serve_deferred(struct hx_cache *hc, struct bio *bio)
{
	sector_t rel = bio->bi_iter.bi_sector;         /* already target-relative */
	unsigned int nblk = bio->bi_iter.bi_size >> 12, b;
	struct bvec_iter it;
	struct bio_vec bv;
	u8 *buf;
	u64 pos = 0;

	buf = kvmalloc(bio->bi_iter.bi_size, GFP_NOIO);
	if (!buf) {
		bio->bi_status = BLK_STS_RESOURCE;
		bio_endio(bio);
		return;
	}
	for (b = 0; b < nblk; b++) {
		if (hx_block_for_read(hc, (rel >> HX_SECT_SHIFT) + b, buf + (size_t)b * HX_BLOCK)) {
			bio->bi_status = BLK_STS_IOERR;
			break;
		}
	}
	if (!bio->bi_status) {
		bio_for_each_segment(bv, bio, it) {
			memcpy_to_bvec(&bv, (const char *)buf + pos);
			pos += bv.bv_len;
		}
	}
	kvfree(buf);
	bio_endio(bio);
}

/* HX_READ_WORKERS of these drain the deferred list together, one bio at a
 * time, so Strand B reads run in parallel instead of queuing behind one. */
static void hx_read_worker(struct work_struct *w)
{
	struct hx_cache *hc = container_of(w, struct hx_reader, work)->hc;
	struct bio *bio;
	unsigned long flags;

	for (;;) {
		spin_lock_irqsave(&hc->defer_lock, flags);
		bio = bio_list_pop(&hc->deferred);
		spin_unlock_irqrestore(&hc->defer_lock, flags);
		if (!bio)
			return;
		hx_serve_deferred(hc, bio);
	}
}

/* ── the Dandelion ──────────────────────────────────────────────────────── */
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

/* Relief: tighten the strands. Keep only `compression` (x1000) of each lane's
 * A blocks raw. Double: cold blocks go to Strand B (the biggest relief).
 * Warm ones (surging only) and, on a single strand, cold ones get compressed.
 * Returns the RAM freed now by compression. The B writer adds what it moves. */
static u64 hx_relieve(struct hx_cache *hc, u8 *buf)
{
	unsigned int budget = HX_Z_PER_TICK, visited;
	u64 freed = 0;
	bool kick = false;

	for (visited = 0; visited < HX_LANES && budget; visited++) {
		struct hx_lane *ln = &hc->lanes[hc->next_lane];
		struct { struct hx_entry *e; struct page *pg; u64 ver; } pick[16];
		unsigned int npick = 0, i, keep_raw;
		struct hx_entry *e, *tmp;
		unsigned long flags;

		hc->next_lane = (hc->next_lane + 1) & (HX_LANES - 1);

		spin_lock_irqsave(&ln->lock, flags);
		keep_raw = (unsigned int)((u64)(ln->count - ln->bcount) * hc->compression / 1000);
		list_for_each_entry_safe(e, tmp, &ln->lru, lru) {
			int t;

			if (ln->pages <= keep_raw + npick || npick == ARRAY_SIZE(pick) || !budget)
				break;
			if (!e->pg || hx_due_soon(e))
				continue;
			t = hx_temp(e);
			if (hc->bdev && t <= HX_TEMP_COLD) {    /* to Strand B */
				hx_set_list(ln, e, HX_ON_PEND);
				kick = true;
				budget--;
				continue;
			}
			if (t > (hc->state == HX_COOL_SURGING ? HX_TEMP_WARM : HX_TEMP_COLD))
				continue;
			get_page(e->pg);
			pick[npick].e = e;
			pick[npick].pg = e->pg;
			pick[npick].ver = e->ver;
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
			if (z && e == pick[i].e && e->ver == pick[i].ver && e->pg == pick[i].pg &&
			    e->where == HX_ON_A) {
				memcpy(z, buf, zlen);
				e->z = z;
				e->zlen = zlen;
				e->pg = NULL;
				ln->pages--;
				ln->zbytes += zlen;
				ln->zcount++;
				hx_newver(hc, e);
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
	hx_kick_writer(hc, kick);
	return freed;
}

struct hx_warm {
	struct list_head node;
	unsigned long first, n;
	unsigned int tries;
};

#define HX_WARM_MAX_PENDING  (1UL << 17)     /* 512 MiB of blocks queued, then drop */
#define HX_WARM_BATCH        128             /* blocks per origin trip when feeding her (512 KiB) */
#define HX_WARM_TRIES        50              /* x 100 ms: wait out a write burst */

/* Read written blocks back from the origin into Strand A. hx_insert refuses a
 * block if any write raced the read (global wgen) or it's already there, so a
 * range that loses the race is retried a little later, once the burst settles. */
static void hx_warm_worker(struct work_struct *w)
{
	struct hx_cache *hc = container_of(to_delayed_work(w), struct hx_cache, warm_work);
	struct hx_warm *wr;
	unsigned long flags, i;
	bool again = false;

	for (;;) {
		spin_lock_irqsave(&hc->warm_lock, flags);
		wr = list_first_entry_or_null(&hc->warm_q, struct hx_warm, node);
		if (wr)
			list_del(&wr->node);
		spin_unlock_irqrestore(&hc->warm_lock, flags);
		if (!wr)
			break;
		if (READ_ONCE(hc->warm_stopping)) {      /* prefetch is only ever "nice to have" */
			kfree(wr);
			continue;
		}
		for (i = 0; i < wr->n && !READ_ONCE(hc->warm_stopping); ) {
			unsigned long idx = wr->first + i;
			struct page **pg = hc->warm_pgs;
			unsigned int n = 0, k;
			u64 gen;

			if (xa_load(&hc->blocks, idx)) {
				i++;                             /* already on her strands */
				continue;
			}
			/* gather the contiguous blocks she doesn't hold: one origin trip */
			while (n < HX_WARM_BATCH && i + n < wr->n && !xa_load(&hc->blocks, idx + n))
				n++;
			if (!pg)
				n = min(n, 1u);
			for (k = 0; k < n; k++) {
				struct page *p = alloc_page(GFP_NOIO | __GFP_NOWARN);

				if (!p)
					break;
				if (pg)
					pg[k] = p;
				else
					put_page(p);
			}
			if (!pg || k < n) {                      /* no memory for a batch: try later */
				while (pg && k--)
					put_page(pg[k]);
				break;
			}
			gen = atomic64_read(&hc->wgen);
			if (hx_sync_read_batch(hc->dev->bdev, (sector_t)idx << HX_SECT_SHIFT, pg, n)) {
				for (k = 0; k < n; k++)
					put_page(pg[k]);
				i += n;
				continue;
			}
			if (atomic64_read(&hc->wgen) != gen) {  /* a write raced: retry later */
				for (k = 0; k < n; k++)
					put_page(pg[k]);
				break;
			}
			for (k = 0; k < n; k++) {
				hx_insert(hc, idx + k, pg[k], gen);   /* takes each reference */
				atomic64_inc(&hc->warmed);
			}
			i += n;
		}
		if (i < wr->n && ++wr->tries < HX_WARM_TRIES) {
			wr->first += i;                     /* keep what's left, try again */
			wr->n -= i;
			spin_lock_irqsave(&hc->warm_lock, flags);
			list_add(&wr->node, &hc->warm_q);
			hc->warm_pending -= i;
			spin_unlock_irqrestore(&hc->warm_lock, flags);
			again = true;
			break;
		}
		spin_lock_irqsave(&hc->warm_lock, flags);
		hc->warm_pending -= wr->n;
		spin_unlock_irqrestore(&hc->warm_lock, flags);
		if (i < wr->n)
			atomic64_add(wr->n - i, &hc->warm_dropped);
		kfree(wr);
	}
	if (again)
		queue_delayed_work(hc->wq, &hc->warm_work, msecs_to_jiffies(100));
}

static void hx_warm_queue(struct hx_cache *hc, sector_t rel, unsigned int sectors)
{
	struct hx_warm *wr;
	unsigned long first, last, flags;

	if (!sectors)
		return;
	first = rel >> HX_SECT_SHIFT;
	last = (rel + sectors - 1) >> HX_SECT_SHIFT;
	wr = kmalloc(sizeof(*wr), GFP_ATOMIC | __GFP_NOWARN);
	spin_lock_irqsave(&hc->warm_lock, flags);
	if (!wr || hc->warm_pending + (last - first + 1) > HX_WARM_MAX_PENDING) {
		spin_unlock_irqrestore(&hc->warm_lock, flags);
		atomic64_add(last - first + 1, &hc->warm_dropped);
		kfree(wr);
		return;
	}
	wr->first = first;
	wr->n = last - first + 1;
	wr->tries = 0;
	list_add_tail(&wr->node, &hc->warm_q);
	hc->warm_pending += wr->n;
	spin_unlock_irqrestore(&hc->warm_lock, flags);
	queue_delayed_work(hc->wq, &hc->warm_work, msecs_to_jiffies(20));
}

static void hx_publish_dandelion(void)
{
	struct hx_cache *hc;
	u32 heat = 0, comp = 1000;
	int state = HX_COOL_COLD, s;

	mutex_lock(&hx_instances_lock);
	list_for_each_entry(hc, &hx_instances, node) {
		heat = max(heat, READ_ONCE(hc->heat));
		comp = min(comp, READ_ONCE(hc->compression));
		s = READ_ONCE(hc->state);
		if (s >= 0 && s < (int)ARRAY_SIZE(hx_heat_rank) &&
		    hx_heat_rank[s] > hx_heat_rank[state])
			state = s;
	}
	mutex_unlock(&hx_instances_lock);
	atomic_set(&helix_dandelion_heat, heat);
	atomic_set(&helix_dandelion_state, state);
	atomic_set(&helix_dandelion_compression, comp);
}

static void hx_dandelion_tick(struct work_struct *w)
{
	struct hx_cache *hc = container_of(to_delayed_work(w), struct hx_cache, tick);
	u64 ops = atomic64_read(&hc->hits) + atomic64_read(&hc->misses) +
		  atomic64_read(&hc->b_hits);
	u64 dops = ops - hc->last_ops;
	u32 io_load, mem_load, load;
	u64 ref;
	unsigned int temps[5] = { 0 }, i;
	unsigned long rungs = 0;
	u64 freed = 0, held = 0, cool;
	u8 *buf;

	hc->last_ops = ops;
	/* Load = ops this tick against a reference. Default: HER OWN peak on this
	 * machine (decaying ~1.5%/tick so she re-learns), never below a floor.
	 * A fixed dandelion_ops_ref overrides. */
	if (dandelion_ops_ref) {
		ref = dandelion_ops_ref;
	} else {
		if (dops > hc->peak_ops)
			hc->peak_ops = dops;
		else
			hc->peak_ops -= hc->peak_ops >> 6;
		ref = max_t(u64, hc->peak_ops, HX_PEAK_FLOOR);
	}
	io_load = (u32)min_t(u64, 1000, div64_u64(dops * 1000 * 1000, (u64)HX_TICK_MS * ref));
	mem_load = helix_mem_pressure_pct() * 10;
	load = max(io_load, mem_load);

	/* OG DoubleHelixStorageSystem.compress()/decompress(), per tick. Heat
	 * rises with load; the OG base cooling (-0.05) applies once load is gone.
	 * Her real cooling is data-driven, below. */
	if (load >= 500) {
		hc->heat = min(1000u, hc->heat + load / 10);
		hc->compression = max(300u, 1000 - load * 7 / 10);
		hc->state = load > 800 ? HX_COOL_SURGING : HX_COOL_HOT;
	} else {
		hc->heat = hc->heat > 50 ? hc->heat - 50 : 0;
		hc->compression = min(1000u, hc->compression + 100);
		hc->state = hc->compression < 1000 ? HX_COOL_COOLING : HX_COOL_COLD;
	}

	if (relief_enabled && hc->compression < 1000) {
		buf = kmalloc(HX_Z_KEEP_MAX, GFP_KERNEL | __GFP_NOWARN);
		if (buf) {
			freed = hx_relieve(hc, buf);
			kfree(buf);
		}
	}
	freed += atomic64_xchg(&hc->b_freed, 0);        /* what moved to Strand B */

	for (i = 0; i < HX_LANES; i++) {
		struct hx_lane *ln = &hc->lanes[i];
		struct hx_entry *e;
		unsigned long flags;

		spin_lock_irqsave(&ln->lock, flags);
		list_for_each_entry(e, &ln->lru, lru) {
			temps[hx_temp(e)]++;
			if (e->bslot)
				rungs++;
		}
		list_for_each_entry(e, &ln->pend, lru)
			temps[hx_temp(e)]++;
		list_for_each_entry(e, &ln->blru, lru)
			temps[hx_temp(e)]++;
		held += (u64)ln->pages * HX_BLOCK + ln->zbytes;
		spin_unlock_irqrestore(&ln->lock, flags);
	}
	memcpy(hc->temps, temps, sizeof(temps));
	hc->rungs = rungs;

	/* "She cools herself with data": freeing 5% of what she holds = -0.05 */
	if (freed) {
		cool = div64_u64(freed * 1000, max_t(u64, 1, held + freed));
		hc->heat = hc->heat > cool ? hc->heat - (u32)cool : 0;
		atomic64_add(freed, &hc->cooled_bytes);
	}
	hx_publish_dandelion();

	schedule_delayed_work(&hc->tick, msecs_to_jiffies(HX_TICK_MS));
}

/* ── device-mapper plumbing ─────────────────────────────────────────────── */
static int hx_map(struct dm_target *ti, struct bio *bio)
{
	struct hx_cache *hc = ti->private;
	struct hx_pb *pb = dm_per_bio_data(bio, sizeof(struct hx_pb));
	sector_t rel = dm_target_offset(ti, bio->bi_iter.bi_sector);
	unsigned long flags;

	pb->fill = false;
	pb->write = false;
	pb->rel = rel;

	switch (bio_op(bio)) {
	case REQ_OP_READ:
		if (!hx_aligned(rel, bio->bi_iter.bi_size)) {
			atomic64_inc(&hc->bypass);
			break;
		}
		switch (hx_try_hit(hc, bio, rel)) {
		case HX_HIT:
			atomic64_inc(&hc->hits);
			bio_endio(bio);
			return DM_MAPIO_SUBMITTED;
		case HX_NEED_B:
			bio->bi_iter.bi_sector = rel;
			spin_lock_irqsave(&hc->defer_lock, flags);
			bio_list_add(&hc->deferred, bio);
			spin_unlock_irqrestore(&hc->defer_lock, flags);
			queue_work(hc->wq, &hc->readers[hc->next_reader++ % HX_READ_WORKERS].work);
			return DM_MAPIO_SUBMITTED;
		case HX_MISS:
			break;
		}
		atomic64_inc(&hc->misses);
		hx_note_miss(hc, rel >> HX_SECT_SHIFT,
			     max_t(unsigned int, 1, bio->bi_iter.bi_size >> (HX_SECT_SHIFT + 9)));
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

	if (pb->write) {
		hx_invalidate(hc, pb->rel, pb->iter.bi_size >> 9);
		if (hc->warm_write && !*error && bio_op(bio) == REQ_OP_WRITE)
			hx_warm_queue(hc, pb->rel, pb->iter.bi_size >> 9);
	} else if (pb->fill && !*error)
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
	vfree(hc->worker_inflate_ws);
}

static void hx_destroy(struct dm_target *ti, struct hx_cache *hc)
{
	if (hc->wq)
		destroy_workqueue(hc->wq);
	bitmap_free(hc->b_map);
	if (hc->bdev)
		dm_put_device(ti, hc->bdev);
	if (hc->dev)
		dm_put_device(ti, hc->dev);
	hx_free_ws(hc);
	kvfree(hc->miss_ring);
	kfree(hc->warm_pgs);
	kfree(hc);
}

static int hx_ctr(struct dm_target *ti, unsigned int argc, char **argv)
{
	struct hx_cache *hc;
	unsigned int ram_mb, i;
	int r, cpu;

	bool warm_write = false;

	if (argc == 3 || argc == 5) {             /* trailing option keyword */
		if (strcmp(argv[argc - 1], "warm_write")) {
			ti->error = "unknown option (only: warm_write)";
			return -EINVAL;
		}
		warm_write = true;
		argc--;
	}
	if (argc != 2 && argc != 4) {
		ti->error = "usage: helix <origin_dev> <ram_mb|auto> [<strandB_dev> <b_mb>] [warm_write]";
		return -EINVAL;
	}
	/* "auto" = her real size: half the machine's RAM (her config was
	 * L1 256 + L2 1024 + L3 3072 MB = "4GB of 8GB"). */
	if (!strcmp(argv[1], "auto"))
		ram_mb = (unsigned int)((totalram_pages() << PAGE_SHIFT) >> 21);
	else if (kstrtouint(argv[1], 10, &ram_mb))
		ram_mb = 0;
	if (!ram_mb || ram_mb > 65536) {
		ti->error = "ram_mb must be 1..65536 or auto";
		return -EINVAL;
	}
	hc = kzalloc(sizeof(*hc), GFP_KERNEL);
	if (!hc) {
		ti->error = "out of memory";
		return -ENOMEM;
	}
	hc->deflate_ws = vzalloc(zlib_deflate_workspacesize(MAX_WBITS, MAX_MEM_LEVEL));
	hc->worker_inflate_ws = vzalloc(zlib_inflate_workspacesize());
	hc->inflate_ws = alloc_percpu(void *);
	r = -ENOMEM;
	ti->error = "out of memory (zlib workspaces)";
	if (!hc->deflate_ws || !hc->worker_inflate_ws || !hc->inflate_ws)
		goto bad;
	for_each_possible_cpu(cpu) {
		void *ws = vzalloc(zlib_inflate_workspacesize());

		if (!ws)
			goto bad;
		*per_cpu_ptr(hc->inflate_ws, cpu) = ws;
	}
	r = dm_get_device(ti, argv[0], dm_table_get_mode(ti->table), &hc->dev);
	if (r) {
		ti->error = "origin device lookup failed";
		goto bad;
	}
	if (argc == 4) {
		unsigned int b_mb;
		u64 dev_bytes;

		r = -EINVAL;
		if (kstrtouint(argv[3], 10, &b_mb) || !b_mb) {
			ti->error = "b_mb must be > 0";
			goto bad;
		}
		r = dm_get_device(ti, argv[2], BLK_OPEN_READ | BLK_OPEN_WRITE, &hc->bdev);
		if (r) {
			ti->error = "strand B device lookup failed";
			goto bad;
		}
		dev_bytes = bdev_nr_bytes(hc->bdev->bdev);
		r = -EINVAL;
		if ((u64)b_mb << 20 > dev_bytes) {
			ti->error = "b_mb is larger than the strand B device";
			goto bad;
		}
		hc->b_mb = b_mb;
		hc->b_slots = ((u64)b_mb << 20) / HX_BLOCK;
		/* the map covers the whole B device, so her paging manager can grow
		 * her budget at runtime (Doppelgangers) without reallocating */
		hc->b_cap_slots = dev_bytes / HX_BLOCK;
		hc->b_map = bitmap_zalloc(hc->b_cap_slots, GFP_KERNEL);
		r = -ENOMEM;
		if (!hc->b_map) {
			ti->error = "out of memory (strand B map)";
			goto bad;
		}
	}
	hc->wq = alloc_workqueue("helix_%s", WQ_MEM_RECLAIM | WQ_UNBOUND, 0, hc->dev->name);
	r = -ENOMEM;
	if (!hc->wq) {
		ti->error = "out of memory (workqueue)";
		goto bad;
	}
	hc->miss_ring = kvcalloc(HX_MISS_RING, sizeof(u64), GFP_KERNEL);   /* optional: no ring, no record */
	hc->warm_pgs = kcalloc(HX_WARM_BATCH, sizeof(struct page *), GFP_KERNEL);
	spin_lock_init(&hc->b_lock);
	spin_lock_init(&hc->defer_lock);
	hc->warm_write = warm_write;
	spin_lock_init(&hc->warm_lock);
	INIT_LIST_HEAD(&hc->warm_q);
	INIT_DELAYED_WORK(&hc->warm_work, hx_warm_worker);
	bio_list_init(&hc->deferred);
	INIT_WORK(&hc->b_write_work, hx_b_writer);
	for (i = 0; i < HX_READ_WORKERS; i++) {
		hc->readers[i].hc = hc;
		INIT_WORK(&hc->readers[i].work, hx_read_worker);
	}

	hc->ram_mb = ram_mb;
	hc->lane_budget = ((u64)ram_mb << 20) / HX_LANES;
	xa_init(&hc->blocks);
	for (i = 0; i < HX_LANES; i++) {
		spin_lock_init(&hc->lanes[i].lock);
		INIT_LIST_HEAD(&hc->lanes[i].lru);
		INIT_LIST_HEAD(&hc->lanes[i].pend);
		INIT_LIST_HEAD(&hc->lanes[i].blru);
	}
	hc->compression = 1000;
	hc->state = HX_COOL_COLD;

	ti->private = hc;
	ti->per_io_data_size = sizeof(struct hx_pb);
	ti->num_flush_bios = 1;
	ti->num_discard_bios = 1;
	ti->num_write_zeroes_bios = 1;

	mutex_lock(&hx_instances_lock);
	list_add_tail(&hc->node, &hx_instances);
	mutex_unlock(&hx_instances_lock);

	INIT_DELAYED_WORK(&hc->tick, hx_dandelion_tick);
	schedule_delayed_work(&hc->tick, msecs_to_jiffies(HX_TICK_MS));
	if (hc->bdev)
		helix_intent_post("double_helix_up %s ram_mb=%u strandB=%s b_mb=%u lanes=%u",
				  hc->dev->name, ram_mb, hc->bdev->name, hc->b_mb, HX_LANES);
	else
		helix_intent_post("helix_up %s ram_mb=%u lanes=%u", hc->dev->name, ram_mb, HX_LANES);
	return 0;
bad:
	hx_destroy(ti, hc);
	return r;
}

static void hx_dtr(struct dm_target *ti)
{
	struct hx_cache *hc = ti->private;
	struct hx_entry *e;
	unsigned long idx, flags;
	unsigned int i;

	mutex_lock(&hx_instances_lock);
	list_del(&hc->node);
	mutex_unlock(&hx_instances_lock);
	hc->warm_write = false;
	WRITE_ONCE(hc->warm_stopping, true);    /* the running pass stops within one origin trip */
	cancel_delayed_work_sync(&hc->warm_work);
	while (!list_empty(&hc->warm_q)) {
		struct hx_warm *wr = list_first_entry(&hc->warm_q, struct hx_warm, node);

		list_del(&wr->node);
		kfree(wr);
	}
	cancel_delayed_work_sync(&hc->tick);
	flush_workqueue(hc->wq);                /* B writer + deferred reads done */
	for (i = 0; i < HX_LANES; i++) {
		struct hx_lane *ln = &hc->lanes[i];
		struct list_head *lists[3] = { &ln->lru, &ln->pend, &ln->blru };
		unsigned int l;

		spin_lock_irqsave(&ln->lock, flags);
		for (l = 0; l < 3; l++) {
			while (!list_empty(lists[l])) {
				e = list_first_entry(lists[l], struct hx_entry, lru);
				xa_erase(&hc->blocks, e->idx);
				hx_free_entry(hc, ln, e);
			}
		}
		spin_unlock_irqrestore(&ln->lock, flags);
	}
	xa_for_each(&hc->blocks, idx, e)
		xa_erase(&hc->blocks, idx);
	xa_destroy(&hc->blocks);
	hx_publish_dandelion();                 /* from the instances still up (cold if none) */
	helix_intent_post("helix_down %s", hc->dev->name);
	hx_destroy(ti, hc);
}

static const char *const hx_state_names[] = { "cold", "warm", "hot", "surging", "cooling" };

static void hx_status(struct dm_target *ti, status_type_t type, unsigned int flags,
		      char *result, unsigned int maxlen)
{
	struct hx_cache *hc = ti->private;
	unsigned long pages = 0, zcount = 0, count = 0, bonly = 0;
	u64 zbytes = 0, pend = 0;
	unsigned int sz = 0, i;

	switch (type) {
	case STATUSTYPE_INFO:
		for (i = 0; i < HX_LANES; i++) {
			count += READ_ONCE(hc->lanes[i].count);
			pages += READ_ONCE(hc->lanes[i].pages);
			zcount += READ_ONCE(hc->lanes[i].zcount);
			zbytes += READ_ONCE(hc->lanes[i].zbytes);
			pend += READ_ONCE(hc->lanes[i].pend_bytes);
			bonly += READ_ONCE(hc->lanes[i].bcount);
		}
		DMEMIT("%s dandelion heat %u.%03u state %s compression %u.%03u lanes %u "
		       "strandA raw %lu zlib5 %lu zbytes %llu pending_bytes %llu "
		       "strandB slots %lu used %lu bonly %lu rungs %lu b_hits %lld b_writes %lld "
		       "b_zero_copy %lld b_evictions %lld b_ioerr %lld "
		       "entries %lu temps frozen %u cold %u warm %u hot %u blazing %u "
		       "hits %lld zhits %lld misses %lld inserts %lld evictions %lld "
		       "invalidations %lld compressed %lld cooled_bytes %lld zfail %lld bypass %lld "
		       "warm_write %d warmed %lld warm_dropped %lld b_cap_slots %lu",
		       hc->bdev ? "double" : "single",
		       hc->heat / 1000, hc->heat % 1000, hx_state_names[hc->state],
		       hc->compression / 1000, hc->compression % 1000, HX_LANES,
		       pages, zcount, zbytes, pend,
		       hc->b_slots, READ_ONCE(hc->b_used), bonly, hc->rungs,
		       atomic64_read(&hc->b_hits), atomic64_read(&hc->b_writes),
		       atomic64_read(&hc->b_zero_copy), atomic64_read(&hc->b_evictions),
		       atomic64_read(&hc->b_ioerr),
		       count, hc->temps[0], hc->temps[1], hc->temps[2], hc->temps[3], hc->temps[4],
		       atomic64_read(&hc->hits), atomic64_read(&hc->zhits),
		       atomic64_read(&hc->misses), atomic64_read(&hc->inserts),
		       atomic64_read(&hc->evictions), atomic64_read(&hc->invalidations),
		       atomic64_read(&hc->compressed), atomic64_read(&hc->cooled_bytes),
		       atomic64_read(&hc->zfail), atomic64_read(&hc->bypass),
		       hc->warm_write ? 1 : 0, atomic64_read(&hc->warmed),
		       atomic64_read(&hc->warm_dropped), hc->b_cap_slots);
		break;
	case STATUSTYPE_TABLE:
		if (hc->bdev)
			DMEMIT("%s %u %s %u", hc->dev->name, hc->ram_mb, hc->bdev->name, hc->b_mb);
		else
			DMEMIT("%s %u", hc->dev->name, hc->ram_mb);
		if (hc->warm_write)
			DMEMIT(" warm_write");
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

/* ── control channel for her paging manager (he clears and feeds her) ──────
 * `dmsetup message <dev> 0 <command>`:
 *   b_budget <mb>            Doppelganger: set Strand B's working budget. Never above
 *                            the whole Strand B device, never below her configured b_mb
 *                            or what she already holds.
 *   prefetch <sector> <n>    feed her: warm n sectors from <sector> (target-relative)
 *                            ahead of demand, through her own bounded warm queue.
 *   misses <since>           what she was asked for and didn't have since sequence <since>,
 *                            merged into runs "start:len" (4 KiB blocks). He predicts from it.
 */
static int hx_message(struct dm_target *ti, unsigned int argc, char **argv,
		      char *result, unsigned int maxlen)
{
	struct hx_cache *hc = ti->private;
	unsigned long flags;

	if (argc == 2 && !strcasecmp(argv[0], "b_budget")) {
		unsigned long want, floor;
		unsigned int mb;

		if (!hc->bdev) {
			DMWARN("helix: b_budget needs a double helix (Strand B)");
			return -EINVAL;
		}
		if (kstrtouint(argv[1], 10, &mb))
			return -EINVAL;
		want = ((u64)mb << 20) / HX_BLOCK;
		spin_lock_irqsave(&hc->b_lock, flags);
		floor = max_t(unsigned long, ((u64)hc->b_mb << 20) / HX_BLOCK, READ_ONCE(hc->b_used));
		hc->b_slots = clamp(want, floor, hc->b_cap_slots);
		spin_unlock_irqrestore(&hc->b_lock, flags);
		return 0;
	}
	if (argc == 3 && !strcasecmp(argv[0], "prefetch")) {
		u64 sector;
		unsigned int n;

		if (kstrtou64(argv[1], 10, &sector) || kstrtouint(argv[2], 10, &n) || !n)
			return -EINVAL;
		if (sector >= ti->len)
			return -EINVAL;
		n = (unsigned int)min_t(u64, n, ti->len - sector);
		hx_warm_queue(hc, (sector_t)sector, n);
		return 0;
	}
	if (argc == 2 && !strcasecmp(argv[0], "misses")) {
		u64 since, cur, from, i, run_start = 0, run_len = 0;
		unsigned int sz = 0;

		if (kstrtou64(argv[1], 10, &since) || !hc->miss_ring)
			return -EINVAL;
		cur = atomic64_read(&hc->miss_seq);
		from = since;
		if (cur > HX_MISS_RING && from < cur - HX_MISS_RING)
			from = cur - HX_MISS_RING;
		if (from > cur)
			from = cur;
		sz += scnprintf(result + sz, maxlen - sz, "seq %llu lost %llu runs", cur, from - min(since, from));
		/* merge consecutive misses into runs: start:len (in 4 KiB blocks) */
		for (i = from; i < cur && sz + 48 < maxlen; i++) {
			u64 e = READ_ONCE(hc->miss_ring[i & (HX_MISS_RING - 1)]);
			u64 idx = e & ((1ULL << 48) - 1), n = e >> 48;

			if (run_len && idx == run_start + run_len) {
				run_len += n;
				continue;
			}
			if (run_len)
				sz += scnprintf(result + sz, maxlen - sz, " %llu:%llu", run_start, run_len);
			run_start = idx;
			run_len = n;
		}
		if (run_len && sz + 48 < maxlen)
			sz += scnprintf(result + sz, maxlen - sz, " %llu:%llu", run_start, run_len);
		if (i < cur)   /* buffer full: tell him where we stopped so he can ask again */
			scnprintf(result + sz, maxlen - sz, " more %llu", i);
		return 1;      /* result filled */
	}
	DMWARN("helix: unknown message (b_budget <mb> | prefetch <sector> <sectors> | misses <since>)");
	return -EINVAL;
}

static struct target_type helix_target = {
	.name            = "helix",
	.version         = {3, 1, 0},
	.module          = THIS_MODULE,
	.ctr             = hx_ctr,
	.dtr             = hx_dtr,
	.map             = hx_map,
	.end_io          = hx_end_io,
	.status          = hx_status,
	.message         = hx_message,
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
