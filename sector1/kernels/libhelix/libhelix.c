/*
 * libhelix.c - HeIX Userspace Library
 * Allows applications to communicate with the HeIX kernel (helix.ko)
 * jwl247 / Jerry Leftwich - GPL
 *
 * Jerry's original library, updated to the current helix.ko:
 *   - device: /dev/helix_intent, falling back to the original /dev/helix_bridge
 *     (helix.ko creates both); override with HELIX_DEVICE=/path
 *   - ABI comes from ../helix.h, the same header the kernel builds with, so
 *     userspace and kernel can't drift apart
 *   - request structs are zeroed before use (the original sent uninitialized
 *     stack bytes to the kernel, and strncpy could leave data_types unterminated)
 *   - merged with the later heix/libhelix.c (the AgnosticLayer bridge):
 *     helix_mem_sync() (ioctl 4) and Virtual Mode when no device is present
 *   - new: helix_get_stats() and helix_read_intent() for the userspace bridge
 *   - messages only when HELIX_VERBOSE is set (a library shouldn't print)
 *
 * Build: cc -O2 -Wall -Wextra -fPIC -shared -o libhelix.so libhelix.c
 */
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include "../helix.h"

static int helix_fd = -1;
static int helix_virtual;

static void helix_log(const char *fmt, ...)
{
	va_list ap;

	if (!getenv("HELIX_VERBOSE"))
		return;
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
}

/* Initialize HeIX connection */
int helix_init(void)
{
	const char *paths[3] = { getenv("HELIX_DEVICE"), "/dev/helix_intent", "/dev/helix_bridge" };
	int i;

	if (helix_fd >= 0)
		return 0;       /* already initialized */
	for (i = 0; i < 3; i++) {
		if (!paths[i])
			continue;
		helix_fd = open(paths[i], O_RDWR | O_CLOEXEC);
		if (helix_fd >= 0) {
			helix_log("HeIX: connected to kernel via %s\n", paths[i]);
			return 0;
		}
	}
	/* No device (helix.ko not loaded): Virtual Mode, as in the original
	 * library. init succeeds so the VMMU can keep running; kernel calls
	 * return -1 with errno ENODEV until a device appears. */
	helix_virtual = 1;
	helix_log("HeIX: no device (%s); running in Virtual Mode\n", strerror(errno));
	return 0;
}

/* 1 when helix_init() found no device and fell back to Virtual Mode. */
int helix_virtual_mode(void)
{
	return helix_virtual;
}

static int helix_ready(void)
{
	if (helix_fd < 0) {
		errno = helix_virtual ? ENODEV : ENOTCONN;
		helix_log("HeIX: %s\n", helix_virtual ? "Virtual Mode: no kernel device"
			  : "not initialized; call helix_init() first");
		return 0;
	}
	return 1;
}

/* Register application with HeIX */
int helix_register(const char *app_name)
{
	struct helix_register_data data;

	if (!helix_ready() || !app_name)
		return -1;
	memset(&data, 0, sizeof(data));
	strncpy(data.app_name, app_name, sizeof(data.app_name) - 1);
	if (ioctl(helix_fd, HELIX_IOCTL_REGISTER, &data) < 0)
		return -1;
	helix_log("HeIX: registered as '%s'\n", data.app_name);
	return 0;
}

/* Join types into "a,b,c" within the kernel's 256-byte field. */
static void helix_join(char *out, size_t outsz, const char **types, int count)
{
	size_t used = 0;
	int i;

	out[0] = '\0';
	for (i = 0; i < count && types && types[i]; i++) {
		size_t len = strlen(types[i]);
		size_t need = len + (used ? 1 : 0);

		if (used + need >= outsz)
			break;  /* never truncate a type name mid-way */
		if (used)
			out[used++] = ',';
		memcpy(out + used, types[i], len);
		used += len;
		out[used] = '\0';
	}
}

/* Declare data types that should stay HOT (in RAM) */
int helix_declare_hot(const char **data_types, int count)
{
	struct helix_hot_data data;

	if (!helix_ready())
		return -1;
	memset(&data, 0, sizeof(data));
	helix_join(data.data_types, sizeof(data.data_types), data_types, count);
	if (ioctl(helix_fd, HELIX_IOCTL_DECLARE_HOT, &data) < 0)
		return -1;
	helix_log("HeIX: declared hot: %s\n", data.data_types);
	return 0;
}

/* Declare data types that can be COLD (skimmed to disk) */
int helix_declare_cold(const char **data_types, int count)
{
	struct helix_cold_data data;

	if (!helix_ready())
		return -1;
	memset(&data, 0, sizeof(data));
	helix_join(data.data_types, sizeof(data.data_types), data_types, count);
	if (ioctl(helix_fd, HELIX_IOCTL_DECLARE_COLD, &data) < 0)
		return -1;
	helix_log("HeIX: declared cold: %s\n", data.data_types);
	return 0;
}

/* Memory Sync: link the Agnostic Layer VMMU's events to the kernel.
 * tier maps to MemoryTier (0 HOT, 1 WARM, 2 COMPRESSED, 3 COLD/FROZEN). */
int helix_mem_sync(uint64_t ptr, size_t size, int tier)
{
	struct helix_memory_event data;

	if (!helix_ready())
		return -1;
	memset(&data, 0, sizeof(data));   /* original left padding uninitialized */
	data.ptr = ptr;
	data.size = size;
	data.target_tier = tier;
	return ioctl(helix_fd, HELIX_IOCTL_MEM_SYNC, &data) < 0 ? -1 : 0;
}

/* Kernel stats snapshot (pressure, slots, apps, intents). */
int helix_get_stats(struct helix_stats *out)
{
	if (!helix_ready() || !out)
		return -1;
	return ioctl(helix_fd, HELIX_IOCTL_GET_STATS, out) < 0 ? -1 : 0;
}

/* Pop one queued intent line into buf (NUL-terminated, newline stripped).
 * Returns its length, 0 if nothing is queued, -1 on error. */
int helix_read_intent(char *buf, size_t len)
{
	ssize_t n;

	if (!helix_ready() || !buf || len < 2)
		return -1;
	n = read(helix_fd, buf, len - 1);
	if (n < 0)
		return -1;
	buf[n] = '\0';
	if (n > 0 && buf[n - 1] == '\n')
		buf[--n] = '\0';
	return (int)n;
}

/* Cleanup */
void helix_cleanup(void)
{
	if (helix_fd >= 0) {
		close(helix_fd);
		helix_fd = -1;
		helix_virtual = 0;
		helix_log("HeIX: disconnected\n");
	}
}
