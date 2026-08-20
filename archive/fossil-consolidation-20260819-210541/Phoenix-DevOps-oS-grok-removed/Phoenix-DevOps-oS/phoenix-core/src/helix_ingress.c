/*
 * helix_ingress.c — Write path for Phoenix Helix C-Core
 * Phoenix DevOps OS / Lost Ark
 *
 * Horseshoe flow (linear, no hidden loops):
 *   file_path
 *     │
 *     ▼  1. Generate hex ID  (SHA-256 of file content)
 *     ▼  2. Build sidecar    (metadata struct → JSON)
 *     ▼  3. Write to R2      (POST to Cloudflare Worker /clonepool)
 *     ▼  4. Write to D1      (POST custody event to Worker /custody)
 *     ▼  5. Write local meta (sidecar.json in trimmed cache dir)
 *     └─ Return result + diagnostic
 *
 * Steps 3-4 require HELIX_WORKER_URL and HELIX_AUTH env vars.
 * Without them, the function completes steps 1-2 and 5 only (offline mode).
 */

#include "../include/helix.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#  include <direct.h>
#  define mkdir_p(p) _mkdir(p)
#else
#  include <sys/stat.h>
#  define mkdir_p(p) mkdir((p), 0755)
#endif

#include "../include/helix_http.h"

static helix_result_t _write_local_sidecar(const helix_sidecar_t* s) {
    /* Write sidecar.json to local trimmed cache dir */
    const char* cache_root = getenv("PHOENIX_CACHE");
    char path[512];
    if (cache_root) {
        snprintf(path, sizeof(path), "%s/%s", cache_root, s->hex_id);
    } else {
#ifdef _WIN32
        snprintf(path, sizeof(path), "C:\\Phoenix\\cache\\%s", s->hex_id);
#else
        snprintf(path, sizeof(path), "%s/.phoenix/cache/%s",
                 getenv("HOME") ? getenv("HOME") : "/tmp", s->hex_id);
#endif
    }

    mkdir_p(path);  /* best-effort — ignore error, sidecar write will fail clearly */

    char sidecar_path[560];
    snprintf(sidecar_path, sizeof(sidecar_path), "%s/sidecar.json", path);

    char* json = helix_sidecar_to_json(s);
    if (!json) {
        helix_log_event("helix_ingress", "local_sidecar",
                        HELIX_ERROR_OOM,
                        "Failed to serialise sidecar to JSON",
                        "Check available memory.");
        return HELIX_ERROR_OOM;
    }

    FILE* f = fopen(sidecar_path, "w");
    if (!f) {
        free(json);
        helix_log_event("helix_ingress", "local_sidecar",
                        HELIX_ERROR_IO,
                        "Could not write local sidecar.json",
                        "Check PHOENIX_CACHE path exists and is writable.");
        return HELIX_ERROR_IO;
    }
    fputs(json, f);
    fclose(f);
    free(json);
    return HELIX_OK;
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC: helix_ingress_intake
 * ══════════════════════════════════════════════════════════════════════════ */

helix_result_t helix_ingress_intake(const char* file_path,
                                    const char* category,
                                    const char* label) {

    /* ── Guard ─────────────────────────────────────────────────────────── */
    if (!file_path) {
        helix_log_event("helix_ingress", "intake",
                        HELIX_ERROR_INVALID_ARG,
                        "file_path is NULL",
                        "Provide a valid file path to intake.");
        return HELIX_ERROR_INVALID_ARG;
    }

    helix_result_t r;

    /* ── Step 1: Build sidecar (hex ID + metadata) ─────────────────────── */
    helix_sidecar_t sidecar;
    r = helix_sidecar_from_file(file_path, category, label, &sidecar);
    if (r != HELIX_OK) return r;  /* diagnostic already posted inside */

    /* ── Step 2: Resolve env config ────────────────────────────────────── */
    const char* worker_url  = getenv("PHOENIX_WORKER_URL");
    const char* auth_token  = getenv("PHOENIX_AUTH");
    int online = (worker_url != NULL && auth_token != NULL);

    /* ── Step 3a: Register metadata in D1 glossary ────────────────────── */
    if (online) {
        r = helix_http_post_clonepool(worker_url, auth_token, &sidecar);
        if (r != HELIX_OK) return r;
    } else {
        helix_log_event("helix_ingress", "intake",
                        HELIX_OK,
                        "PHOENIX_WORKER_URL or PHOENIX_AUTH not set — offline mode",
                        "Set PHOENIX_WORKER_URL and PHOENIX_AUTH to enable R2+D1 sync.");
    }

    /* ── Step 3b: Store file bytes in R2 ──────────────────────────────── */
    if (online) {
        FILE* f = fopen(file_path, "rb");
        if (!f) {
            helix_log_event("helix_ingress", "r2_upload",
                            HELIX_ERROR_IO,
                            "Could not re-open file for R2 upload",
                            "Check file still exists and is readable at the given path.");
        } else {
            fseek(f, 0, SEEK_END);
            long fsz = ftell(f);
            rewind(f);
            if (fsz <= 0) {
                fclose(f);
                helix_log_event("helix_ingress", "r2_upload",
                                HELIX_ERROR_IO,
                                "File reports zero size — skipping R2 byte upload",
                                "Verify the file is not empty before intaking.");
            } else {
                void* fbuf = malloc((size_t)fsz);
                if (!fbuf) {
                    fclose(f);
                    helix_log_event("helix_ingress", "r2_upload",
                                    HELIX_ERROR_OOM,
                                    "malloc failed allocating read buffer for R2 upload",
                                    "Check available system memory or reduce file size.");
                } else {
                    size_t nread = fread(fbuf, 1, (size_t)fsz, f);
                    fclose(f);
                    if (nread != (size_t)fsz) {
                        free(fbuf);
                        helix_log_event("helix_ingress", "r2_upload",
                                        HELIX_ERROR_IO,
                                        "Short read — file may have changed during intake",
                                        "Retry intake. If it persists, check the file for corruption.");
                    } else {
                        r = helix_http_put_content(worker_url, auth_token,
                                                   sidecar.hex_id, fbuf, (size_t)fsz);
                        free(fbuf);
                    }
                }
            }
        }
        /* R2 byte upload is non-fatal — metadata already registered in D1 glossary */
    }

    /* ── Step 4: Write custody event to D1 ─────────────────────────────── */
    if (online) {
        r = helix_http_post_custody(worker_url, auth_token, &sidecar);
        if (r != HELIX_OK) return r;
    }

    /* ── Step 5: Write local sidecar.json ──────────────────────────────── */
    r = _write_local_sidecar(&sidecar);
    if (r != HELIX_OK) return r;

    /* ── Done ───────────────────────────────────────────────────────────── */
    helix_log_event("helix_ingress", "intake",
                    HELIX_OK,
                    "Intake complete",
                    online ? "File registered in R2 + D1 custody."
                           : "File registered locally (offline). Run with PHOENIX_WORKER_URL set to sync.");

    printf("[INGRESS] %s → hex: %s\n", sidecar.name, sidecar.hex_id);
    return HELIX_OK;
}
