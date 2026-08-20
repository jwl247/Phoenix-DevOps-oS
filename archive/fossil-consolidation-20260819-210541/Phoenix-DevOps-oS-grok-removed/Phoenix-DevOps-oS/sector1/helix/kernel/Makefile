# ============================================================
# Makefile — Helix Kernel Module
# Usage: make        (builds helix_kernel.ko)
#        make clean  (removes build artifacts)
#        make load   (insmod)
#        make unload (rmmod)
#        make status (cat /proc/helix_status)
# ============================================================

obj-m += helix_kernel.o

KDIR  := /lib/modules/$(shell uname -r)/build
PWD   := $(shell pwd)

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

load:
	sudo insmod helix_kernel.ko
	@echo "[HELIX] Module loaded"
	@cat /proc/helix_status

unload:
	sudo rmmod helix_kernel
	@echo "[HELIX] Module unloaded"

status:
	@cat /proc/helix_status 2>/dev/null || echo "[HELIX] Module not loaded"

reload: unload load

.PHONY: all clean load unload status reload
