#!/bin/bash
# HeIX Kernel Module Builder

set -e

echo "🔧 HeIX Kernel Module Builder"
echo "=============================="

WORK_DIR="$HOME/helix-module"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# 1. CREATE THE MODULE SOURCE
cat > helix_bridge.c << 'EOF'
/*
 * helix_bridge.c - HeIX Kernel Bridge Module
 * Provides userspace interface to HeIX kernel memory management
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/uaccess.h>
#include <linux/slab.h>

#define HELIX_IOCTL_MAGIC 'H'
#define DEVICE_NAME "helix_bridge"
#define CLASS_NAME "helix"

/* IOCTL command structures */
struct helix_register_data {
    char app_name[64];
};

struct helix_hot_data {
    char data_types[256];
};

/* IOCTL commands */
#define HELIX_IOCTL_REGISTER _IOW(HELIX_IOCTL_MAGIC, 1, struct helix_register_data)
#define HELIX_IOCTL_DECLARE_HOT _IOW(HELIX_IOCTL_MAGIC, 2, struct helix_hot_data)

/* Device variables */
static int major_number;
static struct class *helix_class = NULL;
static struct device *helix_device = NULL;

/* Application registry */
struct helix_app {
    char name[64];
    struct list_head list;
};

static LIST_HEAD(registered_apps);
static DEFINE_SPINLOCK(apps_lock);

/* IOCTL handler */
static long helix_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
    struct helix_register_data reg_data;
    struct helix_hot_data hot_data;
    struct helix_app *app;

    switch (cmd) {
    case HELIX_IOCTL_REGISTER:
        if (copy_from_user(&reg_data, (struct helix_register_data __user *)arg, 
                          sizeof(struct helix_register_data))) {
            return -EFAULT;
        }
        reg_data.app_name[63] = '\0';

        /* Allocate and register app */
        app = kmalloc(sizeof(*app), GFP_KERNEL);
        if (!app)
            return -ENOMEM;

        strncpy(app->name, reg_data.app_name, 63);
        app->name[63] = '\0';

        spin_lock(&apps_lock);
        list_add(&app->list, &registered_apps);
        spin_unlock(&apps_lock);

        printk(KERN_INFO "HeIX: Registered application: %s\n", reg_data.app_name);
        return 0;

    case HELIX_IOCTL_DECLARE_HOT:
        if (copy_from_user(&hot_data, (struct helix_hot_data __user *)arg,
                          sizeof(struct helix_hot_data))) {
            return -EFAULT;
        }
        hot_data.data_types[255] = '\0';
        printk(KERN_INFO "HeIX: Hot data types declared: %s\n", hot_data.data_types);
        return 0;

    default:
        return -ENOTTY;
    }
}

/* File operations */
static int helix_open(struct inode *inode, struct file *file)
{
    printk(KERN_INFO "HeIX: Device opened\n");
    return 0;
}

static int helix_release(struct inode *inode, struct file *file)
{
    printk(KERN_INFO "HeIX: Device closed\n");
    return 0;
}

static struct file_operations fops = {
    .owner = THIS_MODULE,
    .open = helix_open,
    .release = helix_release,
    .unlocked_ioctl = helix_ioctl,
};

/* Module initialization */
static int __init helix_bridge_init(void)
{
    printk(KERN_INFO "HeIX Bridge: Initializing...\n");

    /* Register character device */
    major_number = register_chrdev(0, DEVICE_NAME, &fops);
    if (major_number < 0) {
        printk(KERN_ALERT "HeIX: Failed to register character device\n");
        return major_number;
    }

    /* Create device class */
    helix_class = class_create(CLASS_NAME);
    if (IS_ERR(helix_class)) {
        unregister_chrdev(major_number, DEVICE_NAME);
        printk(KERN_ALERT "HeIX: Failed to create device class\n");
        return PTR_ERR(helix_class);
    }

    /* Create device file */
    helix_device = device_create(helix_class, NULL, MKDEV(major_number, 0),
                                 NULL, DEVICE_NAME);
    if (IS_ERR(helix_device)) {
        class_destroy(helix_class);
        unregister_chrdev(major_number, DEVICE_NAME);
        printk(KERN_ALERT "HeIX: Failed to create device\n");
        return PTR_ERR(helix_device);
    }

    printk(KERN_INFO "HeIX: Device created at /dev/%s\n", DEVICE_NAME);
    printk(KERN_INFO "HeIX: Major number: %d\n", major_number);
    printk(KERN_INFO "HeIX Bridge: Ready\n");

    return 0;
}

/* Module cleanup */
static void __exit helix_bridge_exit(void)
{
    struct helix_app *app, *tmp;

    /* Clean up registered apps */
    spin_lock(&apps_lock);
    list_for_each_entry_safe(app, tmp, &registered_apps, list) {
        list_del(&app->list);
        kfree(app);
    }
    spin_unlock(&apps_lock);

    /* Clean up device in reverse order */
    device_destroy(helix_class, MKDEV(major_number, 0));
    class_destroy(helix_class);
    unregister_chrdev(major_number, DEVICE_NAME);

    printk(KERN_INFO "HeIX Bridge: Exiting\n");
}

module_init(helix_bridge_init);
module_exit(helix_bridge_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("HeIX Team");
MODULE_DESCRIPTION("HeIX Kernel Bridge - Userspace Interface");
MODULE_VERSION("1.0");
EOF

# 2. CREATE MAKEFILE
cat > Makefile << 'EOF'
obj-m += helix_bridge.o

KDIR := /lib/modules/$(shell uname -r)/build

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

install:
	$(MAKE) -C $(KDIR) M=$(PWD) modules_install
	depmod -a

.PHONY: all clean install
EOF

# 3. BUILD THE MODULE
echo ""
echo "📦 Building module..."
make

if [ $? -eq 0 ]; then
    echo "✅ Build successful!"
    echo ""
    echo "📁 Module location: $WORK_DIR/helix_bridge.ko"
    echo ""
    echo "🚀 Next steps:"
    echo "   1. Install: sudo make install"
    echo "   2. Load:    sudo modprobe helix_bridge"
    echo "   3. Verify:  ls -l /dev/helix_bridge"
    echo "   4. Check:   dmesg | tail"
    echo ""
    echo "Or use these quick commands:"
    echo "   Load now:   sudo insmod helix_bridge.ko"
    echo "   Unload:     sudo rmmod helix_bridge"
    echo ""
    
    # Ask if they want to install now
    read -p "Install and load the module now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Installing..."
        sudo make install
        echo "Loading module..."
        sudo modprobe helix_bridge
        echo ""
        echo "Status:"
        lsmod | grep helix_bridge && echo "✅ Module loaded"
        ls -l /dev/helix_bridge 2>/dev/null && echo "✅ Device file created" || echo "❌ Device file not found"
        echo ""
        echo "Kernel messages:"
        dmesg | tail -10 | grep HeIX
    fi
else
    echo "❌ Build failed!"
    echo "Check the errors above."
    exit 1
fi

