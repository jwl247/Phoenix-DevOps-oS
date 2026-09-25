// SPDX-License-Identifier: GPL-2.0
// frank3_slot_a.c — Frank3 Kernel Slot A
// Phoenix DevOps LLC — jwl247
// Builds as frank3_slot_a.ko and sideloads into helix.ko: insmod helix.ko first,
// then this slot. It keeps the original 30 s heartbeat and now also reads
// Helix's memory pressure every tick, posting an intent to userspace when
// pressure crosses Frank's thresholds (60 / 75 / 88 %, from the frank3 design).

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/jiffies.h>
#include "helix.h"

MODULE_LICENSE("GPL");
MODULE_AUTHOR("jwl247");
MODULE_DESCRIPTION("Frank3 Slot A — Phoenix kernel sideload into Helix");
MODULE_VERSION("2.0");

static const int slot_id = 1;
static unsigned long last_beat;
static int last_band = -1;

static int pressure_band(u32 pct)
{
	return pct >= 88 ? 3 : pct >= 75 ? 2 : pct >= 60 ? 1 : 0;
}

static void slot_tick(struct helix_slot *slot, const struct helix_stats *st)
{
	int band = pressure_band(st->mem_pressure_pct);

	if (time_after(jiffies, last_beat + msecs_to_jiffies(30000))) {
		pr_info("frank3_slot_a: heartbeat — slot %d active, pressure %u%%\n",
			slot_id, st->mem_pressure_pct);
		last_beat = jiffies;
	}
	if (band != last_band) {
		helix_intent_post("frank3_slot_a pressure_band=%d pct=%u",
				  band, st->mem_pressure_pct);
		last_band = band;
	}
}

static struct helix_slot slot = {
	.name = "frank3_slot_a",
	.on_tick = slot_tick,
};

static int __init frank3_slot_a_init(void)
{
	last_beat = jiffies;
	return helix_slot_register(&slot);
}

static void __exit frank3_slot_a_exit(void)
{
	helix_slot_unregister(&slot);
}

module_init(frank3_slot_a_init);
module_exit(frank3_slot_a_exit);
