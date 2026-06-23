// frank3_slot_b.c — Frank3 Kernel Module Slot B (failover)
// Phoenix DevOps LLC — jwl247
// Builds as frank3_slot_b.ko — fires at 15s if slot A fails

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/timer.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("jwl247");
MODULE_DESCRIPTION("Frank3 Slot B — Phoenix kernel sideload failover");
MODULE_VERSION("1.0");

static struct timer_list keepalive_timer;
static int slot_id = 2;

static void frank3_heartbeat(struct timer_list *t)
{
    printk(KERN_INFO "frank3_slot_b: heartbeat — slot %d active\n", slot_id);
    mod_timer(&keepalive_timer, jiffies + msecs_to_jiffies(30000));
}

static int __init frank3_slot_b_init(void)
{
    printk(KERN_INFO "frank3_slot_b: loaded — Phoenix kernel slot B active (failover)\n");
    timer_setup(&keepalive_timer, frank3_heartbeat, 0);
    mod_timer(&keepalive_timer, jiffies + msecs_to_jiffies(30000));
    return 0;
}

static void __exit frank3_slot_b_exit(void)
{
    del_timer_sync(&keepalive_timer);
    printk(KERN_INFO "frank3_slot_b: unloaded\n");
}

module_init(frank3_slot_b_init);
module_exit(frank3_slot_b_exit);
