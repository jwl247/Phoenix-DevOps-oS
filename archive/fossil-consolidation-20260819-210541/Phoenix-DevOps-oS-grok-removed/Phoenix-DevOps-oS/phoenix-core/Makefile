# Makefile — phoenix-helix-c
# Phoenix DevOps OS / Lost Ark
#
# Targets:
#   make           → builds libhelix.a
#   make test      → builds + runs smoke tests
#   make intake    → builds the 'phoenix-intake' CLI tool
#   make clean     → removes all build artefacts
#
# Works with:
#   gcc / MinGW-w64 on Windows  (install: winget install GnuWin32.Gcc)
#   gcc on Linux
#
# Windows quick setup:
#   winget install GnuWin32.Gcc
#   - or -
#   winget install MSYS2.MSYS2  (then: pacman -S mingw-w64-x86_64-gcc)
#   Add gcc to PATH, then run: make

CC     = gcc
CFLAGS = -Wall -Wextra -std=c11 -Iinclude

SRC = src/helix_diagnostics.c \
      src/helix_core.c        \
      src/helix_ingress.c     \
      src/helix_egress.c      \
      src/helix_http.c

OBJ    = $(SRC:.c=.o)
LIB    = libhelix.a
TEST   = tests/test_core
INTAKE = tools/phoenix-intake

# ── Default: build static library ───────────────────────────────────────
all: $(LIB)

$(LIB): $(OBJ)
	ar rcs $@ $(OBJ)
	@echo ""
	@echo "  Built $(LIB)"
	@echo "  Next: make test"
	@echo ""

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# ── Tests ────────────────────────────────────────────────────────────────
$(TEST): $(LIB) tests/test_core.c
	$(CC) $(CFLAGS) tests/test_core.c -L. -lhelix -lcurl -o $(TEST)

test: $(TEST)
	@echo ""
	./$(TEST)

# ── CLI tool ─────────────────────────────────────────────────────────────
$(INTAKE): $(LIB) tools/main.c
	$(CC) $(CFLAGS) tools/main.c -L. -lhelix -lcurl -o $(INTAKE)

intake: $(INTAKE)
	@echo "Built $(INTAKE)"

# ── Clean ─────────────────────────────────────────────────────────────────
clean:
	rm -f $(OBJ) $(LIB) $(TEST) $(INTAKE)
	@echo "Clean."

.PHONY: all test intake clean
