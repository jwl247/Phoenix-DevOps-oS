/*
 * libhelix.c - HeIX Userspace Library
 * Comprehensive bridge for Agnostic Layer <-> Kernel communication.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <sys/ioctl.h>

#define HELIX_DEVICE "/dev/helix_bridge"
#define HELIX_IOCTL_MAGIC 'H'

// IOCTL command structures
struct helix_register_data {
    char app_name[64];
};

struct helix_hot_data {
    char data_types[256];
};

struct helix_cold_data {
    char data_types[256];
};

// New structure for Memory Tier Syncing with complete_pkg.py
struct helix_memory_event {
    uint64_t ptr;
    size_t size;
    int target_tier; // Maps to MemoryTier Enum (0=HOT, 2=COMPRESSED)
};

// IOCTL commands
#define HELIX_IOCTL_REGISTER     _IOW(HELIX_IOCTL_MAGIC, 1, struct helix_register_data)
#define HELIX_IOCTL_DECLARE_HOT  _IOW(HELIX_IOCTL_MAGIC, 2, struct helix_hot_data)
#define HELIX_IOCTL_DECLARE_COLD _IOW(HELIX_IOCTL_MAGIC, 3, struct helix_cold_data)
#define HELIX_IOCTL_MEM_SYNC     _IOW(HELIX_IOCTL_MAGIC, 4, struct helix_memory_event)

static int helix_fd = -1;

// Initialize HeIX connection
int helix_init(void) {
    if (helix_fd >= 0) {
        return 0; // Already initialized
    }
    
    helix_fd = open(HELIX_DEVICE, O_RDWR);
    if (helix_fd < 0) {
        perror("HeIX: /dev/helix_bridge not found. Running in Virtual Mode");
        return 0; 
    }
    
    printf("HeIX: Connected to kernel bridge\n");
    return 0;
}

// Register application with HeIX
int helix_register(const char *app_name) {
    struct helix_register_data data;
    if (helix_fd < 0) return -1;
    
    memset(&data, 0, sizeof(data));
    strncpy(data.app_name, app_name, sizeof(data.app_name) - 1);
    data.app_name[sizeof(data.app_name) - 1] = '\0';
    
    if (ioctl(helix_fd, HELIX_IOCTL_REGISTER, &data) < 0) {
        perror("HeIX: Failed to register");
        return -1;
    }
    
    printf("HeIX: Registered as '%s'\n", app_name);
    return 0;
}

// Declare data types that should stay HOT (in L1/L2 RAM)
int helix_declare_hot(const char **data_types, int count) {
    struct helix_hot_data data;
    char buffer[256] = {0};
    
    if (helix_fd < 0) return -1;
    
    for (int i = 0; i < count && strlen(buffer) < 240; i++) {
        if (i > 0) strcat(buffer, ",");
        strncat(buffer, data_types[i], 240 - strlen(buffer));
    }
    
    strncpy(data.data_types, buffer, sizeof(data.data_types) - 1);
    if (ioctl(helix_fd, HELIX_IOCTL_DECLARE_HOT, &data) < 0) {
        perror("HeIX: Failed to declare hot data");
        return -1;
    }
    
    printf("HeIX: Declared hot: %s\n", buffer);
    return 0;
}

// Memory Sync: Link Agnostic Layer VMMU events to Kernel
int helix_mem_sync(uint64_t ptr, size_t size, int tier) {
    struct helix_memory_event data;
    if (helix_fd < 0) return -1;
    
    data.ptr = ptr;
    data.size = size;
    data.target_tier = tier;
    
    return ioctl(helix_fd, HELIX_IOCTL_MEM_SYNC, &data);
}

// Cleanup
void helix_cleanup(void) {
    if (helix_fd >= 0) {
        close(helix_fd);
        helix_fd = -1;
        printf("HeIX: Disconnected\n");
    }
}
