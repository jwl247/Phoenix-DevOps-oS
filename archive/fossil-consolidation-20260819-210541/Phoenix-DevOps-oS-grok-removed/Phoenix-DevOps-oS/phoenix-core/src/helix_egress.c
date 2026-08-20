/*
 * helix_egress.c — Read / resolution path for Phoenix Helix C-Core
 * Phoenix DevOps OS / Lost Ark
 *
 * Horseshoe flow (linear, no hidden loops):
 *   identifier
 *     │
 *     ▼  1. Check local trimmed cache  (fast path — stat + fread)
 *     │       Hit  → return data + update access metadata
 *     │       Miss ↓
 *     ▼  2. Fetch from R2 via Worker   (GET /clonepool/:hex_id)
 *     ▼  3. Store in local cache       (one-way side effect)
 *     ▼  4. Apply bounded prefetch     (one-way side effect, depth-limited)
 *     └─ Return data + diagnostic
 *
 * Requires PHOENIX_WORKER_URL + PHOENIX_AUTH for remote fetch.
 * Falls back to local-only if env vars not set.
 */

#include "../include/helix.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#  include <windows.h>
#  include <direct.h>
#  define mkdir_p(p) _mkdir(p)
#else
#  include <sys/stat.h>
#  define mkdir_p(p) mkdir((p), 0755)
#endif

/* ── Local cache helpers ────────────────────────────────────────────────── */

static void _cache_path(const char* identifier, char* buf, size_t bufsz) {
    const char* root = getenv("PHOENIX_CACHE");
    if (root) {
        snprintf(buf, bufsz, "%s/%s", root, identifier);
    } else {
#ifdef _WIN32
        snprintf(buf, bufsz, "C:\\Phoenix\\cache\\%s", identifier);
#else
        snprintf(buf, bufsz, "%s/.phoenix/cache/%s",
                 getenv("HOME") ? getenv("HOME") : "/tmp", identifier);
#endif
    }
}

static int _cache_hit(const char* identifier) {
    char path[560];
    _cache_path(identifier, path, sizeof(path));
    char content[600];
    snprintf(content, sizeof(content), "%s/content", path);
#ifdef _WIN32
    DWORD attr = GetFileAttributesA(content);
    return (attr != INVALID_FILE_ATTRIBUTES);
#else
    struct stat st;
    return (stat(content, &st) == 0);
#endif
}

static helix_result_t _read_from_cache(const char* identifier,
                                       void** out_data, size_t* out_size) {
    char path[560];
    _cache_path(identifier, path, sizeof(path));
    char content_path[600];
    snprintf(content_path, sizeof(content_path), "%s/content", path);

    FILE* f = fopen(content_path, "rb");
    if (!f) {
        helix_log_event("helix_egress", "cache_read",
                        HELIX_ERROR_NOT_FOUND,
                        "Local content file missing — falling through to R2",
                        "Run intake again to repopulate the local cache.");
        return HELIX_ERROR_NOT_FOUND;
    }

    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    rewind(f);
    if (sz <= 0) {
        fclose(f);
        helix_log_event("helix_egress", "cache_read",
                        HELIX_ERROR_IO,
                        "Local content file is empty or unreadable",
                        "Delete the cache entry and re-run intake to rebuild it.");
        return HELIX_ERROR_IO;
    }

    char* buf = (char*)malloc((size_t)sz + 1);
    if (!buf) {
        fclose(f);
        helix_log_event("helix_egress", "cache_read",
                        HELIX_ERROR_OOM,
                        "malloc failed allocating cache read buffer",
                        "Check available system memory.");
        return HELIX_ERROR_OOM;
    }
    fread(buf, 1, (size_t)sz, f);
    buf[sz] = '\0';
    fclose(f);

    *out_data = buf;
    *out_size = (size_t)sz;
    return HELIX_OK;
}

#include "../include/helix_http.h"

static void _cache_store(const char* identifier,
                         const void* data, size_t size) {
    char path[560];
    _cache_path(identifier, path, sizeof(path));
    mkdir_p(path);
    char content_path[600];
    snprintf(content_path, sizeof(content_path), "%s/content", path);
    FILE* f = fopen(content_path, "wb");
    if (!f) {
        helix_log_event("helix_egress", "cache_store",
                        HELIX_ERROR_IO,
                        "Could not write local content cache file",
                        "Check PHOENIX_CACHE path exists and is writable. "
                        "Next resolve will re-fetch from R2.");
        return;
    }
    fwrite(data, 1, size, f);
    fclose(f);
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC: helix_egress_resolve
 * ══════════════════════════════════════════════════════════════════════════ */

helix_result_t helix_egress_resolve(const char* identifier,
                                    void** output_data,
                                    size_t* output_size) {

    /* ── Guard ─────────────────────────────────────────────────────────── */
    if (!identifier || !output_data || !output_size) {
        helix_log_event("helix_egress", "resolve",
                        HELIX_ERROR_INVALID_ARG,
                        "identifier, output_data, or output_size is NULL",
                        "Provide all three non-NULL arguments.");
        return HELIX_ERROR_INVALID_ARG;
    }

    *output_data = NULL;
    *output_size = 0;

    /* ── Step 1: Local cache check (fast path) ──────────────────────────── */
    if (_cache_hit(identifier)) {
        helix_result_t r = _read_from_cache(identifier, output_data, output_size);
        if (r == HELIX_OK) {
            helix_log_event("helix_egress", "resolve",
                            HELIX_OK,
                            "Cache hit — served from local trimmed cache",
                            NULL);
            return HELIX_OK;
        }
        /* cache file corrupted — fall through to remote */
    }

    /* ── Step 2: Remote fetch via Worker ────────────────────────────────── */
    const char* worker_url = getenv("PHOENIX_WORKER_URL");
    const char* auth_token = getenv("PHOENIX_AUTH");

    if (!worker_url || !auth_token) {
        helix_log_event("helix_egress", "resolve",
                        HELIX_ERROR_NOT_FOUND,
                        "Not in local cache and PHOENIX_WORKER_URL/PHOENIX_AUTH not set",
                        "Set PHOENIX_WORKER_URL and PHOENIX_AUTH, or run 'intake' first.");
        return HELIX_ERROR_NOT_FOUND;
    }

    helix_result_t r = helix_http_get_clonepool(worker_url, auth_token,
                                               identifier, output_data, output_size);
    if (r != HELIX_OK) return r;

    /* ── Step 3: Store in local cache (one-way side effect) ─────────────── */
    if (*output_data && *output_size > 0)
        _cache_store(identifier, *output_data, *output_size);

    helix_log_event("helix_egress", "resolve",
                    HELIX_OK,
                    "Resolved from R2 — cached locally",
                    NULL);
    return HELIX_OK;
}
