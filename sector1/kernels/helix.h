/* SPDX-License-Identifier: GPL-2.0 */
/*
 * helix.h — Phoenix Helix kernel module: shared interface
 * jwl247 / Jerry Leftwich — GPL
 *
 * Two audiences:
 *   - Userspace (Python/Frank) talks to /dev/helix_intent via the ioctls below
 *     and reads queued intents with read().
 *   - Kernel "sideload" modules (Frank's slots) link against helix.ko and plug
 *     in with helix_slot_register(). helix.ko can't be unloaded while a slot
 *     is loaded (the symbol dependency pins it).
 */
#ifndef PHOENIX_HELIX_H
#define PHOENIX_HELIX_H

#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/ioctl.h>
#include <linux/list.h>
#else
#include <stdint.h>
#include <sys/ioctl.h>
typedef uint32_t __u32;
typedef uint64_t __u64;
#endif

#define HELIX_IOCTL_MAGIC 'H'
#define HELIX_NAME_LEN    64
#define HELIX_HOT_LEN     256
#define HELIX_INTENT_LEN  128

struct helix_register_data { char app_name[HELIX_NAME_LEN]; };
struct helix_hot_data      { char data_types[HELIX_HOT_LEN]; };

struct helix_stats {
	__u64 uptime_s;
	__u64 ticks;
	__u64 intents_posted;
	__u64 intents_dropped;
	__u32 mem_pressure_pct;   /* 100 - MemAvailable/MemTotal */
	__u32 apps;
	__u32 slots;
	__u32 intents_queued;
};

#define HELIX_IOCTL_REGISTER    _IOW(HELIX_IOCTL_MAGIC, 1, struct helix_register_data)
#define HELIX_IOCTL_DECLARE_HOT _IOW(HELIX_IOCTL_MAGIC, 2, struct helix_hot_data)
#define HELIX_IOCTL_GET_STATS   _IOR(HELIX_IOCTL_MAGIC, 3, struct helix_stats)

#ifdef __KERNEL__
/* A sideloaded slot. The slot module owns this struct (static storage). */
struct helix_slot {
	const char *name;
	/* Called from Helix's tick (process context, may sleep briefly). */
	void (*on_tick)(struct helix_slot *slot, const struct helix_stats *st);
	void *priv;
	struct list_head node;   /* internal */
};

int  helix_slot_register(struct helix_slot *slot);
void helix_slot_unregister(struct helix_slot *slot);
/* Queue a one-line intent for userspace (read from /dev/helix_intent). */
void helix_intent_post(const char *fmt, ...) __printf(1, 2);
#endif

#endif /* PHOENIX_HELIX_H */
