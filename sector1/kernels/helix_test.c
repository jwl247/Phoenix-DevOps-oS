// helix_test.c — userspace smoke test for helix.ko (/dev/helix_intent)
// Build: make helix_test   Run: sudo ./helix_test   (helix.ko must be loaded)
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "helix.h"

static int fails;
#define CHECK(cond, msg) do { if (cond) printf("  ok   %s\n", msg); \
	else { printf("  FAIL %s (errno %d: %s)\n", msg, errno, strerror(errno)); fails++; } } while (0)

int main(void)
{
	struct helix_register_data reg;
	struct helix_hot_data hot;
	struct helix_stats st0, st;
	char line[256];
	int fd, i, rc, drained = 0, saw_app = 0, saw_hot = 0;

	fd = open("/dev/helix_intent", O_RDONLY);
	CHECK(fd >= 0, "open /dev/helix_intent");
	if (fd < 0)
		return 1;

	CHECK(ioctl(fd, HELIX_IOCTL_GET_STATS, &st0) == 0, "GET_STATS");
	printf("       pressure=%u%% slots=%u apps=%u ticks=%llu\n",
	       st0.mem_pressure_pct, st0.slots, st0.apps, (unsigned long long)st0.ticks);

	memset(&reg, 0, sizeof(reg));
	strcpy(reg.app_name, "helix_test");
	CHECK(ioctl(fd, HELIX_IOCTL_REGISTER, &reg) == 0, "REGISTER helix_test");
	CHECK(ioctl(fd, HELIX_IOCTL_REGISTER, &reg) == 0, "REGISTER duplicate is a no-op");

	memset(&hot, 0, sizeof(hot));
	strcpy(hot.data_types, "blocks:128k,game-assets");
	CHECK(ioctl(fd, HELIX_IOCTL_DECLARE_HOT, &hot) == 0, "DECLARE_HOT");

	CHECK(ioctl(fd, HELIX_IOCTL_GET_STATS, &st) == 0 && st.apps == st0.apps + 1,
	      "app count +1 (duplicate not double-counted)");

	memset(&reg, 0, sizeof(reg));
	errno = 0;
	CHECK(ioctl(fd, HELIX_IOCTL_REGISTER, &reg) == -1 && errno == EINVAL, "empty app name rejected");

	/* unterminated name must not overrun the kernel buffer */
	memset(&reg, 'A', sizeof(reg));
	CHECK(ioctl(fd, HELIX_IOCTL_REGISTER, &reg) == 0, "unterminated 64-byte name handled");

	while ((rc = read(fd, line, sizeof(line) - 1)) > 0) {
		line[rc] = '\0';
		drained++;
		if (strstr(line, "app_registered helix_test")) saw_app = 1;
		if (strstr(line, "hot blocks:128k")) saw_hot = 1;
	}
	CHECK(saw_app && saw_hot, "intents readable (app_registered + hot)");
	printf("       drained %d intent lines\n", drained);

	/* cap: registry must refuse beyond 256 apps rather than grow without bound */
	for (i = 0, rc = 0; i < 300; i++) {
		memset(&reg, 0, sizeof(reg));
		snprintf(reg.app_name, sizeof(reg.app_name), "cap_probe_%d", i);
		if (ioctl(fd, HELIX_IOCTL_REGISTER, &reg) == -1 && errno == ENOSPC) { rc = 1; break; }
	}
	CHECK(rc == 1, "registry capped (ENOSPC before 300 apps)");

	errno = 0;
	CHECK(ioctl(fd, 0xdead, 0) == -1 && errno == ENOTTY, "unknown ioctl -> ENOTTY");

	close(fd);
	printf("\n  %s (%d failure%s)\n", fails ? "FAILED" : "ALL PASSED", fails, fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
