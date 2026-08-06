/*
 * helix_core.c — Core utilities for Phoenix Helix C-Core
 * Phoenix DevOps OS / Lost Ark
 *
 * Provides:
 *   - Deterministic hex ID generation  (SHA-256, self-contained)
 *   - Sidecar creation from file
 *   - Sidecar JSON serialisation
 *
 * Zero external dependencies.  C11.  Compiles on MinGW-w64 + Linux gcc.
 */

#include "../include/helix.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#  include <windows.h>   /* GetFileSize, FILETIME */
#else
#  include <sys/stat.h>
#endif

/* ══════════════════════════════════════════════════════════════════════════
 * SELF-CONTAINED SHA-256
 * Public domain / Unlicence.  No external library needed.
 * ══════════════════════════════════════════════════════════════════════════ */

typedef struct {
    uint32_t state[8];
    uint64_t count;
    uint8_t  buf[64];
} sha256_ctx_t;

static const uint32_t K[64] = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,
    0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,
    0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,
    0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,
    0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,
    0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,
    0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,
    0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,
    0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
};

#define ROR32(x,n) (((x) >> (n)) | ((x) << (32-(n))))
#define CH(x,y,z)  (((x) & (y)) ^ (~(x) & (z)))
#define MAJ(x,y,z) (((x) & (y)) ^ ((x) & (z)) ^ ((y) & (z)))
#define S0(x) (ROR32(x,2)  ^ ROR32(x,13) ^ ROR32(x,22))
#define S1(x) (ROR32(x,6)  ^ ROR32(x,11) ^ ROR32(x,25))
#define s0(x) (ROR32(x,7)  ^ ROR32(x,18) ^ ((x) >> 3))
#define s1(x) (ROR32(x,17) ^ ROR32(x,19) ^ ((x) >> 10))

static void sha256_transform(sha256_ctx_t* ctx, const uint8_t* block) {
    uint32_t w[64], a, b, c, d, e, f, g, h, t1, t2;
    int i;
    for (i = 0; i < 16; i++)
        w[i] = ((uint32_t)block[i*4]<<24) | ((uint32_t)block[i*4+1]<<16)
             | ((uint32_t)block[i*4+2]<< 8) |  (uint32_t)block[i*4+3];
    for (i = 16; i < 64; i++)
        w[i] = s1(w[i-2]) + w[i-7] + s0(w[i-15]) + w[i-16];
    a=ctx->state[0]; b=ctx->state[1]; c=ctx->state[2]; d=ctx->state[3];
    e=ctx->state[4]; f=ctx->state[5]; g=ctx->state[6]; h=ctx->state[7];
    for (i = 0; i < 64; i++) {
        t1 = h + S1(e) + CH(e,f,g) + K[i] + w[i];
        t2 = S0(a) + MAJ(a,b,c);
        h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    ctx->state[0]+=a; ctx->state[1]+=b; ctx->state[2]+=c; ctx->state[3]+=d;
    ctx->state[4]+=e; ctx->state[5]+=f; ctx->state[6]+=g; ctx->state[7]+=h;
}

static void sha256_init(sha256_ctx_t* ctx) {
    ctx->state[0]=0x6a09e667; ctx->state[1]=0xbb67ae85;
    ctx->state[2]=0x3c6ef372; ctx->state[3]=0xa54ff53a;
    ctx->state[4]=0x510e527f; ctx->state[5]=0x9b05688c;
    ctx->state[6]=0x1f83d9ab; ctx->state[7]=0x5be0cd19;
    ctx->count = 0;
}

static void sha256_update(sha256_ctx_t* ctx, const uint8_t* data, size_t len) {
    size_t free = 64 - (size_t)(ctx->count & 63);
    if (len >= free) {
        memcpy(ctx->buf + (ctx->count & 63), data, free);
        sha256_transform(ctx, ctx->buf);
        data += free; len -= free; ctx->count += free;
        for (; len >= 64; data += 64, len -= 64, ctx->count += 64)
            sha256_transform(ctx, data);
        free = 64;
    }
    memcpy(ctx->buf + (ctx->count & 63), data, len);
    ctx->count += len;
}

static void sha256_final(sha256_ctx_t* ctx, uint8_t out[32]) {
    uint8_t pad[64] = {0x80};
    uint64_t bits = ctx->count * 8;
    size_t pos = (size_t)(ctx->count & 63);
    size_t pad_len = (pos < 56) ? (56 - pos) : (120 - pos);
    sha256_update(ctx, pad, pad_len);
    uint8_t len_bytes[8];
    for (int i = 7; i >= 0; i--) { len_bytes[i] = (uint8_t)(bits & 0xff); bits >>= 8; }
    sha256_update(ctx, len_bytes, 8);
    for (int i = 0; i < 8; i++) {
        out[i*4+0] = (uint8_t)(ctx->state[i] >> 24);
        out[i*4+1] = (uint8_t)(ctx->state[i] >> 16);
        out[i*4+2] = (uint8_t)(ctx->state[i] >>  8);
        out[i*4+3] = (uint8_t)(ctx->state[i]      );
    }
}

/* ══════════════════════════════════════════════════════════════════════════
 * HEX ID GENERATION
 * ══════════════════════════════════════════════════════════════════════════ */

helix_result_t helix_generate_hex_id(const uint8_t* data, size_t len,
                                     helix_hex_t out_hex) {
    if (!data || len == 0 || !out_hex) {
        helix_log_event("helix_core", "hex_id",
                        HELIX_ERROR_INVALID_ARG,
                        "data is NULL or zero length",
                        "Provide non-empty data to hash.");
        return HELIX_ERROR_INVALID_ARG;
    }
    sha256_ctx_t ctx;
    uint8_t hash[32];
    sha256_init(&ctx);
    sha256_update(&ctx, data, len);
    sha256_final(&ctx, hash);
    static const char HEX[] = "0123456789abcdef";
    for (int i = 0; i < 32; i++) {
        out_hex[i*2]   = HEX[hash[i] >> 4];
        out_hex[i*2+1] = HEX[hash[i] & 0xf];
    }
    out_hex[64] = '\0';
    return HELIX_OK;
}

helix_result_t helix_hex_id_from_file(const char* file_path,
                                      helix_hex_t out_hex) {
    if (!file_path || !out_hex) {
        helix_log_event("helix_core", "hex_id_from_file",
                        HELIX_ERROR_INVALID_ARG,
                        "file_path or out_hex is NULL",
                        "Provide a valid file path and output buffer.");
        return HELIX_ERROR_INVALID_ARG;
    }

    FILE* f = fopen(file_path, "rb");
    if (!f) {
        helix_log_event("helix_core", "hex_id_from_file",
                        HELIX_ERROR_IO,
                        "Could not open file for reading",
                        "Check the file path exists and is readable.");
        return HELIX_ERROR_IO;
    }

    /* Stream through the file in 64KB chunks — no full-file malloc needed */
    sha256_ctx_t ctx;
    sha256_init(&ctx);
    uint8_t buf[65536];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0)
        sha256_update(&ctx, buf, n);
    fclose(f);

    uint8_t hash[32];
    sha256_final(&ctx, hash);
    static const char HEX[] = "0123456789abcdef";
    for (int i = 0; i < 32; i++) {
        out_hex[i*2]   = HEX[hash[i] >> 4];
        out_hex[i*2+1] = HEX[hash[i] & 0xf];
    }
    out_hex[64] = '\0';
    return HELIX_OK;
}

/* ══════════════════════════════════════════════════════════════════════════
 * SIDECAR CREATION
 * ══════════════════════════════════════════════════════════════════════════ */

static uint64_t _file_size(const char* path) {
#ifdef _WIN32
    WIN32_FILE_ATTRIBUTE_DATA info;
    if (!GetFileAttributesExA(path, GetFileExInfoStandard, &info)) return 0;
    return ((uint64_t)info.nFileSizeHigh << 32) | info.nFileSizeLow;
#else
    struct stat st;
    return (stat(path, &st) == 0) ? (uint64_t)st.st_size : 0;
#endif
}

static void _utc_now(char* buf, size_t bufsz) {
    time_t t = time(NULL);
    struct tm* tm_utc;
#ifdef _WIN32
    tm_utc = gmtime(&t);
#else
    struct tm storage;
    tm_utc = gmtime_r(&t, &storage);
#endif
    strftime(buf, bufsz, "%Y-%m-%dT%H:%M:%SZ", tm_utc);
}

helix_result_t helix_sidecar_from_file(const char* file_path,
                                       const char* category,
                                       const char* label,
                                       helix_sidecar_t* out) {
    if (!file_path || !out) {
        helix_log_event("helix_core", "sidecar_from_file",
                        HELIX_ERROR_INVALID_ARG,
                        "file_path or output sidecar pointer is NULL",
                        "Provide a valid file path and sidecar output.");
        return HELIX_ERROR_INVALID_ARG;
    }

    memset(out, 0, sizeof(*out));

    /* 1. Generate hex ID from file content */
    helix_result_t r = helix_hex_id_from_file(file_path, out->hex_id);
    if (r != HELIX_OK) return r;

    /* 2. Extract filename as name */
    const char* slash = strrchr(file_path, '/');
#ifdef _WIN32
    const char* bslash = strrchr(file_path, '\\');
    if (bslash && (!slash || bslash > slash)) slash = bslash;
#endif
    const char* basename = slash ? slash + 1 : file_path;
    strncpy(out->name, basename, sizeof(out->name) - 1);
    strncpy(out->original_name, basename, sizeof(out->original_name) - 1);

    /* 3. Metadata */
    out->size = _file_size(file_path);
    out->tier = 1;
    strncpy(out->state, "white", sizeof(out->state) - 1);
    if (category) strncpy(out->category, category, sizeof(out->category) - 1);
    if (label)    strncpy(out->label,    label,    sizeof(out->label)    - 1);
    _utc_now(out->intaked_at, sizeof(out->intaked_at));

    /* hex_id doubles as sha3 placeholder until SHA3 is added */
    strncpy(out->hash_sha3, out->hex_id, sizeof(out->hash_sha3) - 1);

    return HELIX_OK;
}

/* ══════════════════════════════════════════════════════════════════════════
 * SIDECAR → JSON
 * Simple manual serialiser — no external JSON library needed.
 * Caller must free() the returned string.
 * ══════════════════════════════════════════════════════════════════════════ */

char* helix_sidecar_to_json(const helix_sidecar_t* s) {
    if (!s) return NULL;

    /* Pre-calculate generous upper bound: all fields + formatting */
    size_t cap = 2048;
    char* buf = (char*)malloc(cap);
    if (!buf) return NULL;

    snprintf(buf, cap,
        "{\n"
        "  \"hex_id\": \"%s\",\n"
        "  \"name\": \"%s\",\n"
        "  \"original_name\": \"%s\",\n"
        "  \"state\": \"%s\",\n"
        "  \"tier\": %d,\n"
        "  \"size\": %llu,\n"
        "  \"hash_sha3\": \"%s\",\n"
        "  \"category\": \"%s\",\n"
        "  \"label\": \"%s\",\n"
        "  \"intaked_at\": \"%s\",\n"
        "  \"notes\": \"%s\"\n"
        "}\n",
        s->hex_id,
        s->name,
        s->original_name,
        s->state,
        s->tier,
        (unsigned long long)s->size,
        s->hash_sha3,
        s->category,
        s->label,
        s->intaked_at,
        s->notes
    );
    return buf;
}
