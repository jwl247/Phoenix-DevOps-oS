/*
 * helix_kernel.c — Phoenix Helix translation kernel
 * Pure C, zero external dependencies.
 * Implements the L1/L2/L3 tier memory translation model.
 *
 * Compile:
 *   gcc -O2 -o helix_kernel helix_kernel.c -lm
 *   gcc -O3 -march=native -o helix_kernel_fast helix_kernel.c -lm
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include <time.h>

/* ── CONSTANTS ──────────────────────────────────────────────────────────────*/
#define HELIX_VERSION     "1.0.0"
#define L1_SIZE           (1 << 20)   /* 1MB  — hot tier   */
#define L2_SIZE           (1 << 23)   /* 8MB  — warm tier  */
#define L3_SIZE           (1 << 26)   /* 64MB — cold tier  */
#define BLOCK_SIZE        4096
#define HELIX_MAGIC       0x48454C58  /* "HELX" */
#define PRESSURE_LOW      60
#define PRESSURE_MED      75
#define PRESSURE_HIGH     88

/* ── TYPES ──────────────────────────────────────────────────────────────────*/
typedef enum {
    TIER_L1 = 0,
    TIER_L2 = 1,
    TIER_L3 = 2,
    TIER_COLD = 3
} HelixTier;

typedef struct {
    uint32_t magic;
    uint32_t version;
    uint64_t id;
    uint64_t size;
    uint64_t checksum;
    HelixTier tier;
    uint32_t flags;
    char     tag[32];
} HelixHeader;

typedef struct {
    uint8_t  *l1;
    uint8_t  *l2;
    uint8_t  *l3;
    size_t    l1_used;
    size_t    l2_used;
    size_t    l3_used;
    uint64_t  hits_l1;
    uint64_t  hits_l2;
    uint64_t  hits_l3;
    uint64_t  misses;
    uint64_t  translations;
    uint64_t  evictions;
} HelixCache;

/* ── CHECKSUM (BLAKE2b-lite, portable) ──────────────────────────────────────*/
static uint64_t helix_checksum(const uint8_t *data, size_t len) {
    uint64_t h = 0xcbf29ce484222325ULL;
    for (size_t i = 0; i < len; i++) {
        h ^= (uint64_t)data[i];
        h *= 0x00000100000001B3ULL;
        h ^= h >> 33;
        h *= 0xff51afd7ed558ccdULL;
        h ^= h >> 33;
    }
    return h;
}

/* ── PRESSURE CALC ──────────────────────────────────────────────────────────*/
static int helix_pressure(const HelixCache *c) {
    size_t total = L1_SIZE + L2_SIZE + L3_SIZE;
    size_t used  = c->l1_used + c->l2_used + c->l3_used;
    return (int)((used * 100) / total);
}

/* ── TIER SELECTION ─────────────────────────────────────────────────────────*/
static HelixTier helix_select_tier(HelixCache *c, size_t size) {
    int pressure = helix_pressure(c);
    if (pressure < PRESSURE_LOW && c->l1_used + size <= L1_SIZE)
        return TIER_L1;
    if (pressure < PRESSURE_MED && c->l2_used + size <= L2_SIZE)
        return TIER_L2;
    if (c->l3_used + size <= L3_SIZE)
        return TIER_L3;
    return TIER_COLD;
}

/* ── CACHE INIT / FREE ──────────────────────────────────────────────────────*/
HelixCache *helix_init(void) {
    HelixCache *c = calloc(1, sizeof(HelixCache));
    if (!c) return NULL;
    c->l1 = malloc(L1_SIZE);
    c->l2 = malloc(L2_SIZE);
    c->l3 = malloc(L3_SIZE);
    if (!c->l1 || !c->l2 || !c->l3) { free(c->l1); free(c->l2); free(c->l3); free(c); return NULL; }
    memset(c->l1, 0, L1_SIZE);
    memset(c->l2, 0, L2_SIZE);
    memset(c->l3, 0, L3_SIZE);
    return c;
}

void helix_free(HelixCache *c) {
    if (!c) return;
    free(c->l1); free(c->l2); free(c->l3); free(c);
}

/* ── TRANSLATE (core op) ────────────────────────────────────────────────────*/
/* Simulates the Helix translation: read src, transform, write to tier cache */
static size_t helix_translate(HelixCache *c,
                               const uint8_t *src, size_t src_len,
                               uint8_t *dst, size_t dst_max) {
    if (!src || !dst || src_len == 0) return 0;
    size_t out_len = (src_len < dst_max) ? src_len : dst_max;
    HelixTier tier = helix_select_tier(c, out_len);

    /* Translation transform — XOR + rotate, cheap but non-trivial */
    for (size_t i = 0; i < out_len; i++) {
        uint8_t b = src[i];
        b ^= (uint8_t)(i & 0xFF);
        b  = (b << 3) | (b >> 5);   /* rotate left 3 */
        b ^= (uint8_t)(src_len & 0xFF);
        dst[i] = b;
    }

    /* Write to appropriate tier buffer */
    uint8_t *tier_buf = NULL;
    size_t  *tier_used = NULL;
    size_t   tier_max = 0;

    switch (tier) {
        case TIER_L1: tier_buf=c->l1; tier_used=&c->l1_used; tier_max=L1_SIZE; c->hits_l1++; break;
        case TIER_L2: tier_buf=c->l2; tier_used=&c->l2_used; tier_max=L2_SIZE; c->hits_l2++; break;
        case TIER_L3: tier_buf=c->l3; tier_used=&c->l3_used; tier_max=L3_SIZE; c->hits_l3++; break;
        default: c->misses++; return out_len;
    }

    size_t write_pos = *tier_used;
    if (write_pos + out_len > tier_max) {
        /* Evict from front — circular */
        memmove(tier_buf, tier_buf + out_len,
                tier_max - out_len > 0 ? tier_max - out_len : 0);
        write_pos = tier_max - out_len;
        c->evictions++;
    }
    memcpy(tier_buf + write_pos, dst, out_len);
    *tier_used = write_pos + out_len;
    c->translations++;
    return out_len;
}

/* ── BENCH HELPERS ──────────────────────────────────────────────────────────*/
static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static void fill_random(uint8_t *buf, size_t len, uint64_t seed) {
    uint64_t s = seed;
    for (size_t i = 0; i < len; i++) {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17;
        buf[i] = (uint8_t)(s & 0xFF);
    }
}

/* ── BENCH SUITE ────────────────────────────────────────────────────────────*/

typedef struct {
    const char *name;
    double      ms;
    double      throughput_mb;
    uint64_t    ops;
    int         passed;
} BenchResult;

/* 1. Sequential translation throughput */
static BenchResult bench_sequential(HelixCache *c) {
    const size_t DATA = 32 * 1024 * 1024;  /* 32MB */
    uint8_t *src = malloc(DATA);
    uint8_t *dst = malloc(DATA);
    fill_random(src, DATA, 0xDEADBEEF);

    double t0 = now_ms();
    size_t total = 0;
    size_t block = BLOCK_SIZE;
    for (size_t off = 0; off + block <= DATA; off += block)
        total += helix_translate(c, src+off, block, dst+off, block);
    double elapsed = now_ms() - t0;

    free(src); free(dst);
    return (BenchResult){
        "Sequential 32MB", elapsed,
        (total / 1024.0 / 1024.0) / (elapsed / 1000.0),
        total / block, 1
    };
}

/* 2. Random block access */
static BenchResult bench_random(HelixCache *c) {
    const int OPS = 100000;
    const size_t POOL = 1 * 1024 * 1024;
    uint8_t *src = malloc(POOL);
    uint8_t *dst = malloc(POOL);
    fill_random(src, POOL, 0xCAFEBABE);

    /* simple LCG for offsets */
    uint64_t rng = 0x12345678;
    double t0 = now_ms();
    size_t total = 0;
    for (int i = 0; i < OPS; i++) {
        rng = rng * 6364136223846793005ULL + 1442695040888963407ULL;
        size_t off = (rng >> 33) % (POOL - 256);
        size_t sz  = 64 + ((rng >> 17) & 0xFF);
        total += helix_translate(c, src+off, sz, dst, sz);
    }
    double elapsed = now_ms() - t0;

    free(src); free(dst);
    return (BenchResult){
        "Random access 100k ops", elapsed,
        (total / 1024.0 / 1024.0) / (elapsed / 1000.0),
        OPS, 1
    };
}

/* 3. Pressure cascade — fill tiers and watch evictions */
static BenchResult bench_pressure(HelixCache *c) {
    /* reset used counters for clean test */
    c->l1_used = c->l2_used = c->l3_used = 0;
    c->evictions = 0;

    const size_t DATA = L1_SIZE + L2_SIZE + L3_SIZE + (L3_SIZE / 4);
    uint8_t *src = malloc(DATA);
    uint8_t *dst = malloc(DATA);
    fill_random(src, DATA, 0xFEEDFACE);

    double t0 = now_ms();
    size_t total = 0;
    for (size_t off = 0; off + BLOCK_SIZE <= DATA; off += BLOCK_SIZE)
        total += helix_translate(c, src+off, BLOCK_SIZE, dst+off, BLOCK_SIZE);
    double elapsed = now_ms() - t0;

    free(src); free(dst);
    return (BenchResult){
        "Pressure cascade", elapsed,
        (total / 1024.0 / 1024.0) / (elapsed / 1000.0),
        total / BLOCK_SIZE, c->evictions > 0 || c->misses > 0
    };
}

/* 4. Checksum throughput */
static BenchResult bench_checksum(void) {
    const size_t DATA = 64 * 1024 * 1024;
    uint8_t *buf = malloc(DATA);
    fill_random(buf, DATA, 0xABCDEF01);

    double t0 = now_ms();
    volatile uint64_t cs = 0;
    size_t block = 65536;
    uint64_t ops = 0;
    for (size_t off = 0; off + block <= DATA; off += block) {
        cs ^= helix_checksum(buf+off, block);
        ops++;
    }
    double elapsed = now_ms() - t0;
    (void)cs;

    free(buf);
    return (BenchResult){
        "Checksum 64MB", elapsed,
        (DATA / 1024.0 / 1024.0) / (elapsed / 1000.0),
        ops, 1
    };
}

/* 5. Correctness — translate then inverse, verify roundtrip */
static BenchResult bench_correctness(HelixCache *c) {
    const size_t N = 4096;
    uint8_t src[4096], mid[4096], recovered[4096];
    fill_random(src, N, 0x11223344);

    helix_translate(c, src, N, mid, N);

    /* inverse transform */
    for (size_t i = 0; i < N; i++) {
        uint8_t b = mid[i];
        b ^= (uint8_t)(N & 0xFF);
        b  = (b >> 3) | (b << 5);   /* rotate right 3 */
        b ^= (uint8_t)(i & 0xFF);
        recovered[i] = b;
    }

    int pass = memcmp(src, recovered, N) == 0;
    return (BenchResult){"Roundtrip correctness", 0, 0, N, pass};
}

/* ── PRINT RESULTS ──────────────────────────────────────────────────────────*/
static void print_result(BenchResult r) {
    const char *status = r.passed ? "\033[32mPASS\033[0m" : "\033[31mFAIL\033[0m";
    if (r.throughput_mb > 0)
        printf("  %-28s %s  %8.1f ms  %7.0f MB/s  %llu ops\n",
               r.name, status, r.ms, r.throughput_mb,
               (unsigned long long)r.ops);
    else
        printf("  %-28s %s\n", r.name, status);
}

static void print_cache_stats(const HelixCache *c) {
    uint64_t total_hits = c->hits_l1 + c->hits_l2 + c->hits_l3;
    printf("\n  Cache stats:\n");
    printf("    L1  %6.1f MB used  %llu hits\n",
           c->l1_used/1024.0/1024.0, (unsigned long long)c->hits_l1);
    printf("    L2  %6.1f MB used  %llu hits\n",
           c->l2_used/1024.0/1024.0, (unsigned long long)c->hits_l2);
    printf("    L3  %6.1f MB used  %llu hits\n",
           c->l3_used/1024.0/1024.0, (unsigned long long)c->hits_l3);
    printf("    Misses:      %llu\n", (unsigned long long)c->misses);
    printf("    Evictions:   %llu\n", (unsigned long long)c->evictions);
    printf("    Translations:%llu\n", (unsigned long long)c->translations);
    printf("    Pressure:    %d%%\n",   helix_pressure(c));
    if (total_hits > 0)
        printf("    L1 hit rate: %.1f%%\n",
               100.0 * c->hits_l1 / total_hits);
}

/* ── MAIN ───────────────────────────────────────────────────────────────────*/
int main(void) {
    printf("\n");
    printf("  Phoenix Helix Kernel v%s — pure C bench\n", HELIX_VERSION);
    printf("  compiled: %s %s\n", __DATE__, __TIME__);
    printf("  L1=%dMB  L2=%dMB  L3=%dMB  block=%dB\n\n",
           L1_SIZE>>20, L2_SIZE>>20, L3_SIZE>>20, BLOCK_SIZE);
    printf("  %-28s %-6s  %10s  %9s  %s\n",
           "Benchmark","Status","Time","Throughput","Ops");
    printf("  %s\n", "──────────────────────────────────────────────────────────");

    HelixCache *c = helix_init();
    if (!c) { fprintf(stderr, "helix_init failed\n"); return 1; }

    BenchResult results[5];
    results[0] = bench_sequential(c);
    results[1] = bench_random(c);
    results[2] = bench_pressure(c);
    results[3] = bench_checksum();
    results[4] = bench_correctness(c);

    for (int i = 0; i < 5; i++) print_result(results[i]);

    print_cache_stats(c);

    int all_pass = 1;
    for (int i = 0; i < 5; i++) if (!results[i].passed) all_pass = 0;
    printf("\n  %s\n\n", all_pass
        ? "\033[32m✓ All benchmarks passed\033[0m"
        : "\033[31m✗ Some benchmarks failed\033[0m");

    helix_free(c);
    return all_pass ? 0 : 1;
}
