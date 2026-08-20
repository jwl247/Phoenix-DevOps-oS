#include <linux/module.h>
#include <linux/fs.h>
#include <linux/device.h>
#include <linux/uaccess.h>
#include <linux/slab.h>

#define DEVICE_NAME "helix_intent"
#define CLASS_NAME "helix"
#define HELIX_IOCTL_MAGIC 'H'

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

static int majorNumber;
static struct class* helixClass = NULL;
static struct device* helixDevice = NULL;

/* Application registry */
struct helix_app {
    char name[64];
    struct list_head list;
};

static LIST_HEAD(registered_apps);
static DEFINE_SPINLOCK(apps_lock);

static int dev_open(struct inode *inodep, struct file *filep) {
    printk(KERN_INFO "HeIX: Device opened\n");
    return 0;
}

static int dev_release(struct inode *inodep, struct file *filep) {
    printk(KERN_INFO "HeIX: Device closed\n");
    return 0;
}

// This allows Python to read the "Intents"
static ssize_t dev_read(struct file *filep, char *buffer, size_t len, loff_t *offset) {
    return 0; // Logic for sending intents goes here later
}

/* IOCTL handler */
static long dev_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
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

static struct file_operations fops = {
    .open = dev_open,
    .release = dev_release,
    .read = dev_read,
    .unlocked_ioctl = dev_ioctl,
};

static int __init bridge_init(void) {
    majorNumber = register_chrdev(0, DEVICE_NAME, &fops);
    if (majorNumber < 0) {
        printk(KERN_ALERT "HeIX: Failed to register character device\n");
        return majorNumber;
    }
    
    helixClass = class_create(CLASS_NAME);
    if (IS_ERR(helixClass)) {
        unregister_chrdev(majorNumber, DEVICE_NAME);
        printk(KERN_ALERT "HeIX: Failed to create device class\n");
        return PTR_ERR(helixClass);
    }
    
    helixDevice = device_create(helixClass, NULL, MKDEV(majorNumber, 0), NULL, DEVICE_NAME);
    if (IS_ERR(helixDevice)) {
        class_destroy(helixClass);
        unregister_chrdev(majorNumber, DEVICE_NAME);
        printk(KERN_ALERT "HeIX: Failed to create device\n");
        return PTR_ERR(helixDevice);
    }
    
    printk(KERN_INFO "🧬 Helix Bridge: /dev/helix_intent created.\n");
    printk(KERN_INFO "HeIX: Ready for userspace communication\n");
    return 0;
}

static void __exit bridge_exit(void) {
    struct helix_app *app, *tmp;

    /* Clean up registered apps */
    spin_lock(&apps_lock);
    list_for_each_entry_safe(app, tmp, &registered_apps, list) {
        list_del(&app->list);
        kfree(app);
    }
    spin_unlock(&apps_lock);

    device_destroy(helixClass, MKDEV(majorNumber, 0));
    class_unregister(helixClass);
    class_destroy(helixClass);
    unregister_chrdev(majorNumber, DEVICE_NAME);
    printk(KERN_INFO "HeIX: Bridge unloaded\n");
}

module_init(bridge_init);
module_exit(bridge_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("HeIX Team");
MODULE_DESCRIPTION("HeIX Kernel Bridge - Userspace Interface");
MODULE_VERSION("1.0");
