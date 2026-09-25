// SPDX-License-Identifier: GPL-2.0
/*
 * dm_helix.c — Helix as an in-kernel block cache (device-mapper target "helix")
 * jwl247 / Jerry Leftwich — GPL. Built into helix.ko.
 *
 * Table line:   <start> <len> helix <origin_dev> <ram_mb>
 *   dmsetup create helix0 --table "0 $(blockdev --getsz /dev/sdX) helix /dev/sdX 512"
 *
 * Helix keeps hot 4 KiB blocks of the origin device in RAM, at the block
 * level: she doesn't care what the bytes are, only how they're used.
 *   READ,  every block cached -> served from RAM, never touches the disk
 *   READ,  any block missing  -> goes to disk; blocks cached on completion
 *   WRITE / DISCARD / ZEROES  -> write-through to disk; cached copies dropped
 *                                when the write is issued AND when it completes
 * A write generation counter guards the race where a read that raced a write
 * could cache pre-write bytes: a read only fills the cache if no write was
 * issued or completed during its lifetime.
 * LRU eviction at <ram_mb>. Cache memory is only ever a copy: removing the
 * target or unloading helix.ko loses nothing.
 */
#define DM_MSG_PREFIX "helix"
#include <linux/module.h>
#include <linux/device-mapper.h>
#include <linux/bio.h>
#include <linux/xarray.h>
#include <linux/highmem.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include "helix.h"

#define HX_BLOCK        4096u
#define HX_SECT_SHIFT   3          /* 8 sectors per 4 KiB block */

struct hx_entry {
	struct page *pg;
	unsigned long idx;
	struct list_head lru;
};

struct hx_cache {
	struct dm_dev *dev;
	unsigned int ram_mb;
	unsigned long max_blocks;
	spinlock_t lock;            /* protects lru, count, xarray contents */
	struct xarray blocks;       /* idx -> struct hx_entry* */
	struct list_head lru;       /* head = coldest */
	unsigned long count;
	atomic64_t wgen;            /* bumped on every write issue + completion */
	atomic64_t hits, misses, inserts, evictions, invalidations, bypass;
};

struct hx_pb {                    /* per-bio data */
	struct bvec_iter iter;      /* iterator as mapped (end_io sees it consumed) */
	sector_t rel;               /* target-relative start sector */
	u64 gen;
	bool fill;                  /* READ miss that may fill the cache */
	bool write;                 /* data-modifying op: invalidate on completion */
};

static void hx_free_entry(struct hx_cache *hc, struct hx_entry *e)
{
	list_del(&e->lru);
	put_page(e->pg);
	kfree(e);
	hc->count--;
}

/* Drop cached blocks overlapping [rel, rel+sectors). Caller holds hc->lock. */
static void hx_invalidate_locked(struct hx_cache *hc, sector_t rel, unsigned int sectors)
{
	unsigned long first, last, idx;
	struct hx_entry *e;

	if (!sectors)
		return;
	first = rel >> HX_SECT_SHIFT;
	last = (rel + sectors - 1) >> HX_SECT_SHIFT;
	xa_for_each_range(&hc->blocks, idx, e, first, last) {
		xa_erase(&hc->blocks, idx);
		hx_free_entry(hc, e);
		atomic64_inc(&hc->invalidations);
	}
}

static void hx_invalidate(struct hx_cache *hc, sector_t rel, unsigned int sectors)
{
	unsigned long flags;

	spin_lock_irqsave(&hc->lock, flags);
	atomic64_inc(&hc->wgen);
	hx_invalidate_locked(hc, rel, sectors);
	spin_unlock_irqrestore(&hc->lock, flags);
}

static bool hx_aligned(sector_t rel, unsigned int bytes)
{
	return bytes && !(rel & ((1 << HX_SECT_SHIFT) - 1)) && !(bytes & (HX_BLOCK - 1));
}

/* Serve a whole READ from cache. Returns false (bio untouched as far as the
 * caller cares) the moment any block is missing. */
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
			struct hx_entry *e;
			struct page *pg;
			unsigned long flags;
			char *src, *dst;

			spin_lock_irqsave(&hc->lock, flags);
			e = xa_load(&hc->blocks, idx);
			if (!e) {
				spin_unlock_irqrestore(&hc->lock, flags);
				return false;
			}
			pg = e->pg;
			get_page(pg);                     /* stays valid if evicted now */
			list_move_tail(&e->lru, &hc->lru);
			spin_unlock_irqrestore(&hc->lock, flags);

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

static void hx_insert(struct hx_cache *hc, unsigned long idx, struct page *pg, u64 gen)
{
	struct hx_entry *e, *old;
	unsigned long flags;

	e = kmalloc(sizeof(*e), GFP_ATOMIC | __GFP_NOWARN);
	if (!e) {
		put_page(pg);
		return;
	}
	e->pg = pg;
	e->idx = idx;

	spin_lock_irqsave(&hc->lock, flags);
	if (atomic64_read(&hc->wgen) != gen) {    /* a write raced this read */
		spin_unlock_irqrestore(&hc->lock, flags);
		put_page(pg);
		kfree(e);
		return;
	}
	old = xa_store(&hc->blocks, idx, e, GFP_ATOMIC | __GFP_NOWARN);
	if (xa_is_err(old)) {
		spin_unlock_irqrestore(&hc->lock, flags);
		put_page(pg);
		kfree(e);
		return;
	}
	if (old)
		hx_free_entry(hc, old);
	list_add_tail(&e->lru, &hc->lru);
	hc->count++;
	atomic64_inc(&hc->inserts);
	while (hc->count > hc->max_blocks) {
		struct hx_entry *cold = list_first_entry(&hc->lru, struct hx_entry, lru);

		xa_erase(&hc->blocks, cold->idx);
		hx_free_entry(hc, cold);
		atomic64_inc(&hc->evictions);
	}
	spin_unlock_irqrestore(&hc->lock, flags);
}

/* Copy a completed READ's data into the cache, 4 KiB block by block. */
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
		put_page(cur);          /* unreachable when aligned; defensive */
}

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
		pb->iter = bio->bi_iter;       /* end_io needs the original length */
		hx_invalidate(hc, rel, bio_sectors(bio));
		break;
	default:
		break;                  /* flushes etc: pass through */
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

static int hx_ctr(struct dm_target *ti, unsigned int argc, char **argv)
{
	struct hx_cache *hc;
	unsigned int ram_mb;
	int r;

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
	r = dm_get_device(ti, argv[0], dm_table_get_mode(ti->table), &hc->dev);
	if (r) {
		ti->error = "origin device lookup failed";
		kfree(hc);
		return r;
	}
	hc->ram_mb = ram_mb;
	hc->max_blocks = (unsigned long)ram_mb * (1024 * 1024 / HX_BLOCK);
	spin_lock_init(&hc->lock);
	xa_init(&hc->blocks);
	INIT_LIST_HEAD(&hc->lru);

	ti->private = hc;
	ti->per_io_data_size = sizeof(struct hx_pb);
	ti->num_flush_bios = 1;
	ti->num_discard_bios = 1;
	ti->num_write_zeroes_bios = 1;
	helix_intent_post("dm_helix_up %s ram_mb=%u", hc->dev->name, ram_mb);
	return 0;
}

static void hx_dtr(struct dm_target *ti)
{
	struct hx_cache *hc = ti->private;
	struct hx_entry *e;
	unsigned long idx, flags;

	spin_lock_irqsave(&hc->lock, flags);
	xa_for_each(&hc->blocks, idx, e) {
		xa_erase(&hc->blocks, idx);
		hx_free_entry(hc, e);
	}
	spin_unlock_irqrestore(&hc->lock, flags);
	xa_destroy(&hc->blocks);
	helix_intent_post("dm_helix_down %s", hc->dev->name);
	dm_put_device(ti, hc->dev);
	kfree(hc);
}

static void hx_status(struct dm_target *ti, status_type_t type, unsigned int flags,
		      char *result, unsigned int maxlen)
{
	struct hx_cache *hc = ti->private;
	unsigned int sz = 0;

	switch (type) {
	case STATUSTYPE_INFO:
		DMEMIT("hits %lld misses %lld inserts %lld evictions %lld invalidations %lld bypass %lld cached_blocks %lu max_blocks %lu",
		       atomic64_read(&hc->hits), atomic64_read(&hc->misses),
		       atomic64_read(&hc->inserts), atomic64_read(&hc->evictions),
		       atomic64_read(&hc->invalidations), atomic64_read(&hc->bypass),
		       READ_ONCE(hc->count), hc->max_blocks);
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
	.version         = {1, 0, 0},
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
