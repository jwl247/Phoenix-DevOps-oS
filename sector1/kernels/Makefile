# Makefile — frank3 kernel module
# Usage:
#   make              — build frank3.ko
#   make clean        — clean build artifacts
#   make load         — insmod (requires root)
#   make unload       — rmmod  (requires root)
#   make status       — cat /proc/frank3
#   make dmesg        — tail kernel log

KVER    ?= $(shell uname -r)
KDIR    ?= /lib/modules/$(KVER)/build
PWD     := $(shell pwd)

obj-m := frank3.o

# Default: build module
all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

# ── LOAD / UNLOAD ─────────────────────────────────────────────────────────────
# Edit DRIVES to match your breach_coms block devices
# Check with: lsblk | grep -E 'sdb|sdc|sdd|sde'
DRIVES ?= /dev/sdb,/dev/sdc,/dev/sdd,/dev/sde

load: frank3.ko
	sudo insmod frank3.ko \
		drives="$(DRIVES)" \
		pressure_low=60 \
		pressure_med=75 \
		pressure_high=88
	@echo "Frank3 loaded. Check: cat /proc/frank3"

unload:
	sudo rmmod frank3
	@echo "Frank3 unloaded."

reload: unload load

status:
	@cat /proc/frank3

dmesg:
	@sudo dmesg | grep frank3 | tail -40

# ── BENCH AGAINST HELIX USERSPACE ────────────────────────────────────────────
bench:
	@echo "=== userspace helix bench ==="
	@cd ../helix-bench && ./helix_O3_v3
	@echo ""
	@echo "=== frank3 kernel stats ==="
	@cat /proc/frank3

.PHONY: all clean load unload reload status dmesg bench
