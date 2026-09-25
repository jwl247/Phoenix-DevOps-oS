# Makefile — Phoenix kernel modules: helix.ko + Frank3 sideload slots
#
#   make           build helix.ko, frank3_slot_a.ko, frank3_slot_b.ko
#   make load      insmod helix, then sideload both Frank slots (root)
#   make unload    remove slots, then helix (root)
#   make status    cat /proc/helix
#   make dmesg     recent helix/frank3 kernel log lines
#   make test      userspace smoke test against /dev/helix_intent (root)
#   make clean
#
# Linux only. Needs linux-headers-$(uname -r). Helix must be loaded before any
# slot: slots link against helix.ko's exported symbols (helix_slot_register),
# and the kernel refuses to unload helix while a slot still uses it.

KVER ?= $(shell uname -r)
KDIR ?= /lib/modules/$(KVER)/build
PWD  := $(shell pwd)

obj-m := helix.o frank3_slot_a.o frank3_slot_b.o
helix-objs := helix_kmod.o

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean
	rm -f helix_test

load: all
	sudo insmod helix.ko
	sudo insmod frank3_slot_a.ko
	sudo insmod frank3_slot_b.ko
	@cat /proc/helix

unload:
	-sudo rmmod frank3_slot_b
	-sudo rmmod frank3_slot_a
	-sudo rmmod helix

reload: unload load

status:
	@cat /proc/helix

dmesg:
	@sudo dmesg | grep -E 'helix|frank3' | tail -40

helix_test: helix_test.c helix.h
	$(CC) -Wall -Wextra -O2 -o $@ helix_test.c

test: helix_test
	sudo ./helix_test

.PHONY: all clean load unload reload status dmesg test
