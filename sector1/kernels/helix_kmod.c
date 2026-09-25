// SPDX-License-Identifier: GPL-2.0
/*
 * helix_kmod.c — Phoenix Helix kernel module (builds as helix.ko)
 * jwl247 / Jerry Leftwich — GPL
 *
 * Grown from Jerry's helix_intent bridge (HeIX Kernel Bridge v1.0):
 *   /dev/helix_intent   ioctl REGISTER / DECLARE_HOT (unchanged ABI) + GET_STATS,
 *                       read() now returns queued intents, one line per read.
 *   /proc/helix         human-readable status: pressure, apps, slots, intents.
 *   sideload registry   Frank's slot modules plug in via helix_slot_register()
 *                       and get a pressure tick every tick_ms.
 *
 * Fixes vs the bridge: exit no longer calls class_unregister() before
 * class_destroy() (that freed the class twice); the app registry is capped and
 * de-duplicated (was unbounded kmalloc from any opener); fops has .owner.
 */
#include <linux/module.h>
#include <linux/fs.h>
#include <linux/device.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/workqueue.h>
#include <linux/jiffies.h>
#include <linux/mm.h>
#include <linux/string.h>
#include "helix.h"

#define DEVICE_NAME   "helix_intent"
#define CLASS_NAME    "helix"
#define HELIX_VERSION "2.0"
#define MAX_APPS      256
#define INTENT_RING   256   /* must be a power of two */

static unsigned int tick_ms = 5000;
module_param(tick_ms, uint, 0444);
MODULE_PARM_DESC(tick_ms, "Slot tick interval in ms (default 5000)");

/* ── device ─────────────────────────────────────────────────────────────── */
static int major_number;
static struct class *helix_class;
static struct device *helix_device;
static struct proc_dir_entry *helix_proc;
static unsigned long load_jiffies;

/* ── app registry (from the bridge) ─────────────────────────────────────── */
struct helix_app {
	char name[HELIX_NAME_LEN];
	struct list_head list;
};
static LIST_HEAD(registered_apps);
static DEFINE_MUTEX(apps_lock);
static unsigned int app_count;

/* ── sideload slots ─────────────────────────────────────────────────────── */
static LIST_HEAD(slots);
static DEFINE_MUTEX(slots_lock);
static unsigned int slot_count;
static u64 ticks;
static struct delayed_work tick_work;

/* ── intent ring: kernel/slots post, userspace reads ────────────────────── */
static char intents[INTENT_RING][HELIX_INTENT_LEN];
static unsigned int intent_head, intent_tail;  /* head = next write */
static DEFINE_SPINLOCK(intent_lock);
static u64 intents_posted, intents_dropped;

void helix_intent_post(const char *fmt, ...)
{
	char line[HELIX_INTENT_LEN];
	unsigned long flags;
	va_list args;

	va_start(args, fmt);
	vscnprintf(line, sizeof(line), fmt, args);
	va_end(args);

	spin_lock_irqsave(&intent_lock, flags);
	if (intent_head - intent_tail >= INTENT_RING) {
		intent_tail++;            /* ring full: drop the oldest */
		intents_dropped++;
	}
	strscpy(intents[intent_head & (INTENT_RING - 1)], line, HELIX_INTENT_LEN);
	intent_head++;
	intents_posted++;
	spin_unlock_irqrestore(&intent_lock, flags);
}
EXPORT_SYMBOL_GPL(helix_intent_post);

static u32 helix_mem_pressure(void)
{
	unsigned long total = totalram_pages();
	unsigned long avail = si_mem_available();

	if (!total)
		return 0;
	if (avail > total)
		avail = total;
	return (u32)(100 - (avail * 100) / total);
}

static void helix_fill_stats(struct helix_stats *st)
{
	unsigned long flags;

	memset(st, 0, sizeof(*st));
	st->uptime_s = jiffies_to_msecs(jiffies - load_jiffies) / 1000;
	st->ticks = READ_ONCE(ticks);
	st->mem_pressure_pct = helix_mem_pressure();
	st->apps = READ_ONCE(app_count);
	st->slots = READ_ONCE(slot_count);
	spin_lock_irqsave(&intent_lock, flags);
	st->intents_posted = intents_posted;
	st->intents_dropped = intents_dropped;
	st->intents_queued = intent_head - intent_tail;
	spin_unlock_irqrestore(&intent_lock, flags);
}

int helix_slot_register(struct helix_slot *slot)
{
	struct helix_slot *s;

	if (!slot || !slot->name)
		return -EINVAL;
	mutex_lock(&slots_lock);
	list_for_each_entry(s, &slots, node) {
		if (s == slot || !strcmp(s->name, slot->name)) {
			mutex_unlock(&slots_lock);
			return -EEXIST;
		}
	}
	list_add_tail(&slot->node, &slots);
	slot_count++;
	mutex_unlock(&slots_lock);
	pr_info("helix: slot '%s' sideloaded\n", slot->name);
	helix_intent_post("slot_loaded %s", slot->name);
	return 0;
}
EXPORT_SYMBOL_GPL(helix_slot_register);

void helix_slot_unregister(struct helix_slot *slot)
{
	mutex_lock(&slots_lock);   /* waits out an in-progress tick */
	list_del_init(&slot->node);
	slot_count--;
	mutex_unlock(&slots_lock);
	pr_info("helix: slot '%s' unloaded\n", slot->name);
	helix_intent_post("slot_unloaded %s", slot->name);
}
EXPORT_SYMBOL_GPL(helix_slot_unregister);

static void helix_tick(struct work_struct *w)
{
	struct helix_stats st;
	struct helix_slot *s;

	WRITE_ONCE(ticks, ticks + 1);
	helix_fill_stats(&st);
	mutex_lock(&slots_lock);
	list_for_each_entry(s, &slots, node)
		if (s->on_tick)
			s->on_tick(s, &st);
	mutex_unlock(&slots_lock);
	schedule_delayed_work(&tick_work, msecs_to_jiffies(tick_ms));
}

/* ── /dev/helix_intent ──────────────────────────────────────────────────── */
static ssize_t dev_read(struct file *filp, char __user *buf, size_t len, loff_t *off)
{
	char line[HELIX_INTENT_LEN + 1];
	unsigned long flags;
	size_t n;

	spin_lock_irqsave(&intent_lock, flags);
	if (intent_head == intent_tail) {
		spin_unlock_irqrestore(&intent_lock, flags);
		return 0;                 /* nothing queued */
	}
	strscpy(line, intents[intent_tail & (INTENT_RING - 1)], HELIX_INTENT_LEN);
	intent_tail++;
	spin_unlock_irqrestore(&intent_lock, flags);

	n = strlen(line);
	line[n++] = '\n';
	if (len < n)
		n = len;                  /* short buffer: truncate, don't split */
	if (copy_to_user(buf, line, n))
		return -EFAULT;
	return n;
}

static long dev_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)
{
	struct helix_register_data reg;
	struct helix_hot_data hot;
	struct helix_stats st;
	struct helix_app *app;

	switch (cmd) {
	case HELIX_IOCTL_REGISTER:
		if (copy_from_user(&reg, (void __user *)arg, sizeof(reg)))
			return -EFAULT;
		reg.app_name[HELIX_NAME_LEN - 1] = '\0';
		if (!reg.app_name[0])
			return -EINVAL;
		mutex_lock(&apps_lock);
		list_for_each_entry(app, &registered_apps, list) {
			if (!strcmp(app->name, reg.app_name)) {
				mutex_unlock(&apps_lock);
				return 0;         /* already registered */
			}
		}
		if (app_count >= MAX_APPS) {
			mutex_unlock(&apps_lock);
			return -ENOSPC;
		}
		app = kmalloc(sizeof(*app), GFP_KERNEL);
		if (!app) {
			mutex_unlock(&apps_lock);
			return -ENOMEM;
		}
		strscpy(app->name, reg.app_name, HELIX_NAME_LEN);
		list_add(&app->list, &registered_apps);
		app_count++;
		mutex_unlock(&apps_lock);
		pr_info("helix: registered application: %s\n", reg.app_name);
		helix_intent_post("app_registered %s", reg.app_name);
		return 0;

	case HELIX_IOCTL_DECLARE_HOT:
		if (copy_from_user(&hot, (void __user *)arg, sizeof(hot)))
			return -EFAULT;
		hot.data_types[HELIX_HOT_LEN - 1] = '\0';
		pr_info("helix: hot data types declared: %s\n", hot.data_types);
		helix_intent_post("hot %.100s", hot.data_types);
		return 0;

	case HELIX_IOCTL_GET_STATS:
		helix_fill_stats(&st);
		if (copy_to_user((void __user *)arg, &st, sizeof(st)))
			return -EFAULT;
		return 0;

	default:
		return -ENOTTY;
	}
}

static const struct file_operations fops = {
	.owner = THIS_MODULE,
	.read = dev_read,
	.unlocked_ioctl = dev_ioctl,
	.compat_ioctl = compat_ptr_ioctl,
	.llseek = noop_llseek,
};

/* ── /proc/helix ────────────────────────────────────────────────────────── */
static int helix_proc_show(struct seq_file *m, void *v)
{
	struct helix_stats st;
	struct helix_app *app;
	struct helix_slot *s;

	helix_fill_stats(&st);
	seq_printf(m, "helix %s\nuptime_s %llu\nticks %llu\ntick_ms %u\n",
		   HELIX_VERSION, st.uptime_s, st.ticks, tick_ms);
	seq_printf(m, "mem_pressure_pct %u\n", st.mem_pressure_pct);
	seq_printf(m, "intents queued=%u posted=%llu dropped=%llu\n",
		   st.intents_queued, st.intents_posted, st.intents_dropped);
	seq_printf(m, "slots %u\n", st.slots);
	mutex_lock(&slots_lock);
	list_for_each_entry(s, &slots, node)
		seq_printf(m, "  slot %s\n", s->name);
	mutex_unlock(&slots_lock);
	seq_printf(m, "apps %u\n", st.apps);
	mutex_lock(&apps_lock);
	list_for_each_entry(app, &registered_apps, list)
		seq_printf(m, "  app %s\n", app->name);
	mutex_unlock(&apps_lock);
	return 0;
}

/* ── init / exit ────────────────────────────────────────────────────────── */
static int __init helix_init(void)
{
	if (tick_ms < 100)
		tick_ms = 100;
	load_jiffies = jiffies;

	major_number = register_chrdev(0, DEVICE_NAME, &fops);
	if (major_number < 0) {
		pr_alert("helix: failed to register character device\n");
		return major_number;
	}
	helix_class = class_create(CLASS_NAME);
	if (IS_ERR(helix_class)) {
		unregister_chrdev(major_number, DEVICE_NAME);
		return PTR_ERR(helix_class);
	}
	helix_device = device_create(helix_class, NULL, MKDEV(major_number, 0),
				     NULL, DEVICE_NAME);
	if (IS_ERR(helix_device)) {
		class_destroy(helix_class);
		unregister_chrdev(major_number, DEVICE_NAME);
		return PTR_ERR(helix_device);
	}
	helix_proc = proc_create_single("helix", 0444, NULL, helix_proc_show);
	if (!helix_proc)
		pr_warn("helix: /proc/helix not created\n");

	INIT_DELAYED_WORK(&tick_work, helix_tick);
	schedule_delayed_work(&tick_work, msecs_to_jiffies(tick_ms));

	pr_info("helix: v%s ready — /dev/%s, /proc/helix, tick %ums\n",
		HELIX_VERSION, DEVICE_NAME, tick_ms);
	helix_intent_post("helix_ready v%s", HELIX_VERSION);
	return 0;
}

static void __exit helix_exit(void)
{
	struct helix_app *app, *tmp;

	cancel_delayed_work_sync(&tick_work);
	proc_remove(helix_proc);

	mutex_lock(&apps_lock);
	list_for_each_entry_safe(app, tmp, &registered_apps, list) {
		list_del(&app->list);
		kfree(app);
	}
	mutex_unlock(&apps_lock);

	device_destroy(helix_class, MKDEV(major_number, 0));
	class_destroy(helix_class);   /* also unregisters; no class_unregister() */
	unregister_chrdev(major_number, DEVICE_NAME);
	pr_info("helix: unloaded\n");
}

module_init(helix_init);
module_exit(helix_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("jwl247 (Jerry Leftwich)");
MODULE_DESCRIPTION("Phoenix Helix kernel module — intent bridge, /proc/helix, Frank sideload slots");
MODULE_VERSION(HELIX_VERSION);
