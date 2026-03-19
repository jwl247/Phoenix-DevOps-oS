// ============================================================
// helix_kernel.c — Helix Kernel Module
// Project:   Phoenix DevOps / Full Propagator Framework
// Author:    jwl247 / Phoenix DevOps LLC
// License:   GPL-3.0
// ============================================================
// Loadable kernel module for the Helix translation layer.
// Provides LD_PRELOAD hook via libhelix.so and FUSE mount
// at opt2 for filesystem-level transparent operation.
//
// Load:   insmod helix_kernel.ko
// Unload: rmmod helix_kernel
// Status: cat /proc/helix_status
// ============================================================

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/version.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("jwl247 / Phoenix DevOps LLC");
MODULE_DESCRIPTION("Helix Translation Layer Kernel Module");
MODULE_VERSION("1.4.0");

#define HELIX_PROC_NAME     "helix_status"
#define HELIX_VERSION       "1.4.0"
#define HELIX_MOUNT_POINT   "/opt2"
#define HELIX_LIB_PATH      "/opt2/VMCOMS/julietshouse/libhelix.so"
#define HELIX_CONFIG_PATH   "/opt2/VMCOMS/julietshouse/helix_mesh.conf"
#define HELIX_UPSTREAM      "/opt2/VMCOMS/julietshouse/upstream_brain"
#define HELIX_DOWNSTREAM    "/opt2/VMCOMS/julietshouse/downstream_storage"

// ── Module State ─────────────────────────────────────────────
static struct proc_dir_entry *helix_proc_entry;
static int helix_active = 0;
static unsigned long helix_msg_count = 0;
static char helix_tier[8] = "L1";

// ── /proc/helix_status ───────────────────────────────────────
static int helix_status_show(struct seq_file *m, void *v)
{
    seq_printf(m, "helix_kernel v%s\n", HELIX_VERSION);
    seq_printf(m, "active:      %d\n", helix_active);
    seq_printf(m, "tier:        %s\n", helix_tier);
    seq_printf(m, "msg_count:   %lu\n", helix_msg_count);
    seq_printf(m, "mount:       %s\n", HELIX_MOUNT_POINT);
    seq_printf(m, "lib:         %s\n", HELIX_LIB_PATH);
    seq_printf(m, "config:      %s\n", HELIX_CONFIG_PATH);
    seq_printf(m, "upstream:    %s\n", HELIX_UPSTREAM);
    seq_printf(m, "downstream:  %s\n", HELIX_DOWNSTREAM);
    return 0;
}

static int helix_status_open(struct inode *inode, struct file *file)
{
    return single_open(file, helix_status_show, NULL);
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 6, 0)
static const struct proc_ops helix_proc_ops = {
    .proc_open    = helix_status_open,
    .proc_read    = seq_read,
    .proc_lseek   = seq_lseek,
    .proc_release = single_release,
};
#else
static const struct file_operations helix_proc_ops = {
    .owner   = THIS_MODULE,
    .open    = helix_status_open,
    .read    = seq_read,
    .llseek  = seq_lseek,
    .release = single_release,
};
#endif

// ── Module Init ──────────────────────────────────────────────
static int __init helix_kernel_init(void)
{
    printk(KERN_INFO "helix_kernel: loading v%s\n", HELIX_VERSION);

    helix_proc_entry = proc_create(
        HELIX_PROC_NAME, 0444, NULL, &helix_proc_ops
    );

    if (!helix_proc_entry) {
        printk(KERN_ERR "helix_kernel: failed to create /proc/%s\n",
               HELIX_PROC_NAME);
        return -ENOMEM;
    }

    helix_active = 1;
    printk(KERN_INFO "helix_kernel: /proc/%s created\n", HELIX_PROC_NAME);
    printk(KERN_INFO "helix_kernel: mount point %s\n", HELIX_MOUNT_POINT);
    printk(KERN_INFO "helix_kernel: ready — LP load and fuse\n");

    return 0;
}

// ── Module Exit ──────────────────────────────────────────────
static void __exit helix_kernel_exit(void)
{
    helix_active = 0;
    if (helix_proc_entry)
        proc_remove(helix_proc_entry);
    printk(KERN_INFO "helix_kernel: unloaded\n");
}

module_init(helix_kernel_init);
module_exit(helix_kernel_exit);
