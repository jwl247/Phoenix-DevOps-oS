// frank3_slot_a.c — Frank3 Kernel Module Slot A
// Phoenix DevOps LLC — jwl247
// Builds as frank3_slot_a.ko — sideloads 10s post-boot

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/timer.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("jwl247");
MODULE_DESCRIPTION("Frank3 Slot A — Phoenix kernel sideload");
MODULE_VERSION("1.0");

static struct timer_list keepalive_timer;
static int slot_id = 1;

static void frank3_heartbeat(struct timer_list *t)
{
    printk(KERN_INFO "frank3_slot_a: heartbeat — slot %d active\n", slot_id);
    mod_timer(&keepalive_timer, jiffies + msecs_to_jiffies(30000));
}

static int __init frank3_slot_a_init(void)
{
    printk(KERN_INFO "frank3_slot_a: loaded — Phoenix kernel slot A active\n");
    timer_setup(&keepalive_timer, frank3_heartbeat, 0);
    mod_timer(&keepalive_timer, jiffies + msecs_to_jiffies(30000));
    return 0;
}

static void __exit frank3_slot_a_exit(void)
{
    del_timer_sync(&keepalive_timer);
    printk(KERN_INFO "frank3_slot_a: unloaded\n");
}

module_init(frank3_slot_a_init);
module_exit(frank3_slot_a_exit);
