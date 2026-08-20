# Simple Makefile for phoenix-helix-c
# Works with MinGW on Windows or gcc on Linux

CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -Iinclude

SRC = src/helix_diagnostics.c \
      src/helix_ingress.c \
      src/helix_egress.c \
      src/helix_core.c

OBJ = $(SRC:.c=.o)
TARGET = libhelix.a

all: $(TARGET)

$(TARGET): $(OBJ)
	ar rcs $@ $(OBJ)
	@echo "Built $(TARGET)"

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJ) $(TARGET)

.PHONY: all clean
