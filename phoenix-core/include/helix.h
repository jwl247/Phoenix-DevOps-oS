#ifndef HELIX_H
#define HELIX_H

#include <stdint.h>
#include <stddef.h>

/*
 * helix.h — Public API for Phoenix Helix C-Core
 * Phoenix DevOps OS / Lost Ark
 *
 * Design rules:
 *   - Horseshoe / daisy chain flow in all hot paths (no hidden loops)
 *   - Fail fast with rich diagnostics
 *   - Every event auto-posts: What + Why + Recommended Action
 *   - Zero external dependencies in core (libcurl added only for HTTP)
 *   - C11, compiles with gcc or MinGW-w64 on Windows / Linux
 */

/* ── Result codes ───────────────────────────────────────────────────────── */

typedef enum {
    HELIX_OK                  = 0,
    HELIX_ERROR_GENERIC       = 1,
    HELIX_ERROR_INVALID_ARG   = 2,
    HELIX_ERROR_HEX_COLLISION = 3,
    HELIX_ERROR_R2_WRITE      = 4,
    HELIX_ERROR_R2_READ       = 5,
    HELIX_ERROR_D1_WRITE      = 6,
    HELIX_ERROR_NOT_FOUND     = 7,
    HELIX_ERROR_IO            = 8,
    HELIX_ERROR_OOM           = 9,
    HELIX_ERROR_INTERNAL      = 10
} helix_result_t;

/* ── Diagnostic / journal type ──────────────────────────────────────────── */

typedef struct {
    const char*    component;           /* e.g. "helix_ingress"      */
    const char*    operation;           /* e.g. "hex_generation"     */
    helix_result_t result;
    const char*    reason;              /* specific reason for event */
    const char*    recommended_action;  /* suggested next step       */
} helix_diagnostic_t;

/* ── Hex ID type (64 hex chars = 32 bytes SHA-256, NUL terminated) ──────── */

#define HELIX_HEX_LEN 64
typedef char helix_hex_t[HELIX_HEX_LEN + 1];

/* ── Sidecar (metadata for one clonepool entry) ─────────────────────────── */

typedef struct {
    helix_hex_t hex_id;         /* deterministic SHA-256 of file content  */
    char        name[256];      /* registered name                        */
    char        original_name[256];
    char        state[32];      /* "white" | "green" | "red" etc.         */
    int         tier;           /* 1–4                                    */
    uint64_t    size;           /* bytes                                  */
    char        hash_sha3[128]; /* full SHA3-256 hex (for audit)          */
    char        category[64];
    char        label[128];
    char        intaked_at[32]; /* ISO-8601 UTC                           */
    char        notes[512];
} helix_sidecar_t;

/* ══════════════════════════════════════════════════════════════════════════
 * DIAGNOSTIC / JOURNALING API  (always available, no deps)
 * ══════════════════════════════════════════════════════════════════════════ */

/* Post a structured diagnostic event — prints What + Why + Recommended Action */
void helix_post_diagnostic(const helix_diagnostic_t* diag);

/* Convenience wrapper — build and post in one call */
void helix_log_event(const char* component, const char* operation,
                     helix_result_t result, const char* reason,
                     const char* recommended_action);

/* Retrieve the last posted diagnostic (useful for callers) */
const helix_diagnostic_t* helix_get_last_diagnostic(void);

/* ══════════════════════════════════════════════════════════════════════════
 * CORE UTILITIES  (helix_core.c)
 * ══════════════════════════════════════════════════════════════════════════ */

/*
 * Generate deterministic hex ID from arbitrary bytes.
 * Uses SHA-256.  Output is 64 lowercase hex chars + NUL in out_hex.
 * Returns HELIX_OK or HELIX_ERROR_INVALID_ARG.
 */
helix_result_t helix_generate_hex_id(const uint8_t* data, size_t len,
                                     helix_hex_t out_hex);

/*
 * Generate hex ID directly from a file path (reads file content).
 * Returns HELIX_OK, HELIX_ERROR_IO, or HELIX_ERROR_INVALID_ARG.
 */
helix_result_t helix_hex_id_from_file(const char* file_path,
                                      helix_hex_t out_hex);

/* Fill a helix_sidecar_t from a file path + metadata */
helix_result_t helix_sidecar_from_file(const char* file_path,
                                       const char* category,
                                       const char* label,
                                       helix_sidecar_t* out);

/* Serialise a sidecar to a JSON string.  Caller must free() the result. */
char* helix_sidecar_to_json(const helix_sidecar_t* s);

/* ══════════════════════════════════════════════════════════════════════════
 * INGRESS  (helix_ingress.c) — write path, horseshoe flow
 * ══════════════════════════════════════════════════════════════════════════ */

helix_result_t helix_ingress_intake(const char* file_path,
                                    const char* category,
                                    const char* label);

/* ══════════════════════════════════════════════════════════════════════════
 * EGRESS  (helix_egress.c) — read / resolve path, horseshoe flow
 * ══════════════════════════════════════════════════════════════════════════ */

helix_result_t helix_egress_resolve(const char* identifier,
                                    void** output_data,
                                    size_t* output_size);

#endif /* HELIX_H */
