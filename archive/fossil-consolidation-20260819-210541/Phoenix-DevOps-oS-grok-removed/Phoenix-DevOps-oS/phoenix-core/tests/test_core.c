/*
 * tests/test_core.c — Smoke tests for helix_core (hex ID + sidecar)
 * Run: make test
 * Produces: tests/test_core  (or test_core.exe on Windows)
 */

#include "../include/helix.h"
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <stdlib.h>

static int pass = 0, fail = 0;

#define ASSERT_EQ(label, a, b) do { \
    if ((a) == (b)) { printf("  [PASS] %s\n", label); pass++; } \
    else { printf("  [FAIL] %s  (got %d, want %d)\n", label, (int)(a), (int)(b)); fail++; } \
} while(0)

#define ASSERT_STR_LEN(label, s, n) do { \
    if (strlen(s) == (size_t)(n)) { printf("  [PASS] %s\n", label); pass++; } \
    else { printf("  [FAIL] %s  (len=%zu, want %d)\n", label, strlen(s), (int)(n)); fail++; } \
} while(0)

#define ASSERT_STR_NE(label, a, b) do { \
    if (strcmp((a),(b)) != 0) { printf("  [PASS] %s\n", label); pass++; } \
    else { printf("  [FAIL] %s  (strings should differ)\n", label); fail++; } \
} while(0)

/* ── Test 1: hex ID from data ─────────────────────────────────────────── */
static void test_hex_id_basic(void) {
    printf("\n--- test_hex_id_basic ---\n");
    helix_hex_t hex;
    helix_result_t r;

    /* Known SHA-256 of "hello" =
       2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824 */
    const uint8_t hello[] = "hello";
    r = helix_generate_hex_id(hello, 5, hex);
    ASSERT_EQ("returns HELIX_OK", r, HELIX_OK);
    ASSERT_STR_LEN("hex is 64 chars", hex, 64);
    ASSERT_EQ("known SHA-256 of 'hello'",
        strcmp(hex, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"),
        0);

    /* Different input → different hex */
    helix_hex_t hex2;
    const uint8_t world[] = "world";
    helix_generate_hex_id(world, 5, hex2);
    ASSERT_STR_NE("different inputs produce different IDs", hex, hex2);
}

/* ── Test 2: hex ID is deterministic ──────────────────────────────────── */
static void test_hex_id_deterministic(void) {
    printf("\n--- test_hex_id_deterministic ---\n");
    helix_hex_t hex_a, hex_b;
    const uint8_t data[] = "Phoenix DevOps OS Lost Ark";
    helix_generate_hex_id(data, sizeof(data)-1, hex_a);
    helix_generate_hex_id(data, sizeof(data)-1, hex_b);
    ASSERT_EQ("same input always produces same hex",
              strcmp(hex_a, hex_b), 0);
}

/* ── Test 3: null / empty guard ───────────────────────────────────────── */
static void test_hex_id_guards(void) {
    printf("\n--- test_hex_id_guards ---\n");
    helix_hex_t hex;
    helix_result_t r;

    r = helix_generate_hex_id(NULL, 5, hex);
    ASSERT_EQ("NULL data returns INVALID_ARG", r, HELIX_ERROR_INVALID_ARG);

    const uint8_t d[] = "x";
    r = helix_generate_hex_id(d, 0, hex);
    ASSERT_EQ("zero length returns INVALID_ARG", r, HELIX_ERROR_INVALID_ARG);

    r = helix_generate_hex_id(d, 1, NULL);
    ASSERT_EQ("NULL out_hex returns INVALID_ARG", r, HELIX_ERROR_INVALID_ARG);
}

/* ── Test 4: sidecar JSON from data ───────────────────────────────────── */
static void test_sidecar_json(void) {
    printf("\n--- test_sidecar_json ---\n");
    helix_sidecar_t s;
    memset(&s, 0, sizeof(s));
    strcpy(s.hex_id, "aabbccdd");
    strcpy(s.name, "myfile.txt");
    strcpy(s.state, "white");
    s.tier = 1;
    s.size = 1234;
    strcpy(s.intaked_at, "2026-06-27T12:00:00Z");

    char* json = helix_sidecar_to_json(&s);
    ASSERT_EQ("sidecar_to_json returns non-NULL", json != NULL, 1);
    if (json) {
        ASSERT_EQ("JSON contains hex_id", strstr(json, "aabbccdd") != NULL, 1);
        ASSERT_EQ("JSON contains name",   strstr(json, "myfile.txt") != NULL, 1);
        ASSERT_EQ("JSON contains state",  strstr(json, "white") != NULL, 1);
        free(json);
    }
}

/* ── Test 5: ingress null guard ───────────────────────────────────────── */
static void test_ingress_null_guard(void) {
    printf("\n--- test_ingress_null_guard ---\n");
    helix_result_t r = helix_ingress_intake(NULL, NULL, NULL);
    ASSERT_EQ("NULL file_path returns INVALID_ARG", r, HELIX_ERROR_INVALID_ARG);
}

/* ── Test 6: egress null guard ────────────────────────────────────────── */
static void test_egress_null_guard(void) {
    printf("\n--- test_egress_null_guard ---\n");
    void* data = NULL; size_t sz = 0;
    helix_result_t r;
    r = helix_egress_resolve(NULL, &data, &sz);
    ASSERT_EQ("NULL identifier returns INVALID_ARG", r, HELIX_ERROR_INVALID_ARG);
    r = helix_egress_resolve("abc", NULL, &sz);
    ASSERT_EQ("NULL output_data returns INVALID_ARG", r, HELIX_ERROR_INVALID_ARG);
    r = helix_egress_resolve("abc", &data, NULL);
    ASSERT_EQ("NULL output_size returns INVALID_ARG", r, HELIX_ERROR_INVALID_ARG);
}

/* ─────────────────────────────────────────────────────────────────────── */

int main(void) {
    printf("╔══════════════════════════════════════════╗\n");
    printf("║  phoenix-helix-c  smoke tests            ║\n");
    printf("╚══════════════════════════════════════════╝\n");

    test_hex_id_basic();
    test_hex_id_deterministic();
    test_hex_id_guards();
    test_sidecar_json();
    test_ingress_null_guard();
    test_egress_null_guard();

    printf("\n══════════════════════════════════════════\n");
    printf("  Results: %d passed, %d failed\n", pass, fail);
    printf("══════════════════════════════════════════\n\n");
    return (fail == 0) ? 0 : 1;
}
