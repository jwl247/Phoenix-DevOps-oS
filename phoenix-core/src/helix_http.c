/*
 * helix_http.c — HTTP layer for Phoenix Helix C-Core
 * Phoenix DevOps OS / Lost Ark
 *
 * Wires ingress and egress to the Cloudflare Worker over HTTPS.
 * Requires libcurl (-lcurl).
 *
 * Endpoints (PHOENIX_WORKER_URL):
 *   POST /clonepool          — register file in R2 + D1 glossary
 *   POST /custody            — append intake event to D1 custody ledger
 *   GET  /clonepool/:hex_id  — fetch content from R2
 *
 * Auth: Authorization: Bearer <PHOENIX_AUTH> header on every request.
 */

#include "../include/helix_http.h"
#include <curl/curl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ══════════════════════════════════════════════════════════════════════════
 * INTERNAL: response buffer + write callback
 * ══════════════════════════════════════════════════════════════════════════ */

typedef struct {
    char*  ptr;
    size_t len;
} http_buf_t;

static size_t _write_cb(void* data, size_t size, size_t nmemb, void* userp) {
    size_t   total = size * nmemb;
    http_buf_t* buf = (http_buf_t*)userp;
    char* tmp = (char*)realloc(buf->ptr, buf->len + total + 1);
    if (!tmp) return 0;  /* curl reports CURLE_WRITE_ERROR on 0 */
    buf->ptr = tmp;
    memcpy(buf->ptr + buf->len, data, total);
    buf->len += total;
    buf->ptr[buf->len] = '\0';
    return total;
}

/* ══════════════════════════════════════════════════════════════════════════
 * INTERNAL: base58 encode — first 8 bytes of hex_id → TAV short address
 *
 * TAV spec: SHA3-512 → first 8 bytes → base58.
 * We derive b58 from the first 8 bytes of the SHA-256 hex_id until
 * SHA3-512 is added to helix_core.c. Same determinism guarantee applies.
 * ══════════════════════════════════════════════════════════════════════════ */

static const char B58[] = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

static void _b58_from_hex(const char* hex, char* out, size_t outsz) {
    uint64_t n = 0;
    for (int i = 0; i < 16 && hex[i]; i++) {
        char c = hex[i];
        uint8_t v = (c >= 'a') ? (uint8_t)(c - 'a' + 10)
                  : (c >= 'A') ? (uint8_t)(c - 'A' + 10)
                  :              (uint8_t)(c - '0');
        n = (n << 4) | v;
    }
    char tmp[16];
    int pos = 0;
    do {
        tmp[pos++] = B58[n % 58];
        n /= 58;
    } while (n > 0 && pos < 15);
    size_t w = ((size_t)pos < outsz - 1) ? (size_t)pos : outsz - 1;
    for (size_t i = 0; i < w; i++)
        out[i] = tmp[pos - 1 - (int)i];
    out[w] = '\0';
}

/* ══════════════════════════════════════════════════════════════════════════
 * INTERNAL: shared curl init — URL, auth header, write callback
 * Returns NULL on failure (caller logs and returns HELIX_ERROR_INTERNAL).
 * Caller must curl_slist_free_all(*hdrs) + curl_easy_cleanup(curl).
 * ══════════════════════════════════════════════════════════════════════════ */

static CURL* _curl_init(const char* url, const char* auth_token,
                        struct curl_slist** hdrs_out, http_buf_t* resp) {
    CURL* curl = curl_easy_init();
    if (!curl) return NULL;

    char auth_hdr[512];
    snprintf(auth_hdr, sizeof(auth_hdr), "Authorization: Bearer %s", auth_token);

    struct curl_slist* hdrs = NULL;
    hdrs = curl_slist_append(hdrs, "Content-Type: application/json");
    hdrs = curl_slist_append(hdrs, auth_hdr);
    *hdrs_out = hdrs;

    resp->ptr = NULL;
    resp->len = 0;

    curl_easy_setopt(curl, CURLOPT_URL,           url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER,    hdrs);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, _write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA,     resp);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT,       30L);

    const char* ca = getenv("CURL_CA_BUNDLE");
    if (ca) curl_easy_setopt(curl, CURLOPT_CAINFO, ca);

    return curl;
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC: helix_http_post_clonepool
 * POST /clonepool
 *   required: hex_id, b58, name
 *   optional: original_name, state, tier, size, hash_sha3, category, label, notes
 * ══════════════════════════════════════════════════════════════════════════ */

helix_result_t helix_http_post_clonepool(const char* worker_url,
                                         const char* auth_token,
                                         const helix_sidecar_t* s) {
    char b58[16];
    _b58_from_hex(s->hex_id, b58, sizeof(b58));

    char url[512];
    snprintf(url, sizeof(url), "%s/clonepool", worker_url);

    char payload[4096];
    snprintf(payload, sizeof(payload),
        "{"
        "\"hex_id\":\"%s\","
        "\"b58\":\"%s\","
        "\"name\":\"%s\","
        "\"original_name\":\"%s\","
        "\"state\":\"%s\","
        "\"tier\":%d,"
        "\"size\":%llu,"
        "\"hash_sha3\":\"%s\","
        "\"category\":\"%s\","
        "\"label\":\"%s\","
        "\"notes\":\"%s\""
        "}",
        s->hex_id, b58, s->name, s->original_name,
        s->state, s->tier, (unsigned long long)s->size,
        s->hash_sha3, s->category, s->label, s->notes);

    struct curl_slist* hdrs = NULL;
    http_buf_t resp = {NULL, 0};
    CURL* curl = _curl_init(url, auth_token, &hdrs, &resp);
    if (!curl) {
        helix_log_event("helix_http", "post_clonepool",
                        HELIX_ERROR_INTERNAL,
                        "curl_easy_init() failed",
                        "Check libcurl is installed and linked correctly.");
        return HELIX_ERROR_INTERNAL;
    }

    curl_easy_setopt(curl, CURLOPT_POST,       1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload);

    CURLcode res = curl_easy_perform(curl);
    long http_code = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    curl_slist_free_all(hdrs);
    curl_easy_cleanup(curl);
    free(resp.ptr);

    if (res != CURLE_OK) {
        helix_log_event("helix_http", "post_clonepool",
                        HELIX_ERROR_R2_WRITE,
                        curl_easy_strerror(res),
                        "Check PHOENIX_WORKER_URL and network connectivity.");
        return HELIX_ERROR_R2_WRITE;
    }
    if (http_code < 200 || http_code >= 300) {
        helix_log_event("helix_http", "post_clonepool",
                        HELIX_ERROR_R2_WRITE,
                        "Worker returned non-2xx status",
                        "Check Worker logs, PHOENIX_AUTH token, and worker deployment.");
        return HELIX_ERROR_R2_WRITE;
    }

    helix_log_event("helix_http", "post_clonepool",
                    HELIX_OK, "Registered in R2 clonepool", NULL);
    return HELIX_OK;
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC: helix_http_post_custody
 * POST /custody
 *   required: name, hex_id, action
 *   optional: state, actor, validated
 * D1 custody is append-only — this call never mutates existing records.
 * ══════════════════════════════════════════════════════════════════════════ */

helix_result_t helix_http_post_custody(const char* worker_url,
                                       const char* auth_token,
                                       const helix_sidecar_t* s) {
    char url[512];
    snprintf(url, sizeof(url), "%s/custody", worker_url);

    char payload[1024];
    snprintf(payload, sizeof(payload),
        "{"
        "\"name\":\"%s\","
        "\"hex_id\":\"%s\","
        "\"action\":\"intake\","
        "\"state\":\"%s\","
        "\"actor\":\"phoenix-intake\","
        "\"validated\":false"
        "}",
        s->name, s->hex_id, s->state);

    struct curl_slist* hdrs = NULL;
    http_buf_t resp = {NULL, 0};
    CURL* curl = _curl_init(url, auth_token, &hdrs, &resp);
    if (!curl) {
        helix_log_event("helix_http", "post_custody",
                        HELIX_ERROR_INTERNAL,
                        "curl_easy_init() failed",
                        "Check libcurl is installed and linked correctly.");
        return HELIX_ERROR_INTERNAL;
    }

    curl_easy_setopt(curl, CURLOPT_POST,       1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload);

    CURLcode res = curl_easy_perform(curl);
    long http_code = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    curl_slist_free_all(hdrs);
    curl_easy_cleanup(curl);
    free(resp.ptr);

    if (res != CURLE_OK) {
        helix_log_event("helix_http", "post_custody",
                        HELIX_ERROR_D1_WRITE,
                        curl_easy_strerror(res),
                        "Check PHOENIX_WORKER_URL and network connectivity.");
        return HELIX_ERROR_D1_WRITE;
    }
    if (http_code < 200 || http_code >= 300) {
        helix_log_event("helix_http", "post_custody",
                        HELIX_ERROR_D1_WRITE,
                        "Worker returned non-2xx status",
                        "Check Worker logs and PHOENIX_AUTH token.");
        return HELIX_ERROR_D1_WRITE;
    }

    helix_log_event("helix_http", "post_custody",
                    HELIX_OK, "Custody event appended to D1", NULL);
    return HELIX_OK;
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC: helix_http_put_content
 * PUT /clonepool/:hex_id — store raw file bytes in R2 via worker
 * ══════════════════════════════════════════════════════════════════════════ */

helix_result_t helix_http_put_content(const char* worker_url,
                                      const char* auth_token,
                                      const char* hex_id,
                                      const void* data,
                                      size_t      data_len) {
    char url[512];
    snprintf(url, sizeof(url), "%s/clonepool/%s", worker_url, hex_id);

    struct curl_slist* hdrs = NULL;
    http_buf_t resp = {NULL, 0};
    CURL* curl = _curl_init(url, auth_token, &hdrs, &resp);
    if (!curl) {
        helix_log_event("helix_http", "put_content",
                        HELIX_ERROR_INTERNAL,
                        "curl_easy_init() failed",
                        "Check libcurl is installed and linked correctly.");
        return HELIX_ERROR_INTERNAL;
    }

    /* Override Content-Type to octet-stream for binary upload */
    curl_slist_free_all(hdrs);
    hdrs = NULL;
    char auth_hdr[512];
    snprintf(auth_hdr, sizeof(auth_hdr), "Authorization: Bearer %s", auth_token);
    hdrs = curl_slist_append(hdrs, "Content-Type: application/octet-stream");
    hdrs = curl_slist_append(hdrs, auth_hdr);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, hdrs);

    curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST,    "PUT");
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS,       data);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE,    (long)data_len);

    CURLcode res = curl_easy_perform(curl);
    long http_code = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    curl_slist_free_all(hdrs);
    curl_easy_cleanup(curl);
    free(resp.ptr);

    if (res != CURLE_OK) {
        helix_log_event("helix_http", "put_content",
                        HELIX_ERROR_R2_WRITE,
                        curl_easy_strerror(res),
                        "Check PHOENIX_WORKER_URL and network connectivity.");
        return HELIX_ERROR_R2_WRITE;
    }
    if (http_code < 200 || http_code >= 300) {
        helix_log_event("helix_http", "put_content",
                        HELIX_ERROR_R2_WRITE,
                        "Worker returned non-2xx on content PUT",
                        "Check Worker logs and PHOENIX_AUTH token.");
        return HELIX_ERROR_R2_WRITE;
    }

    helix_log_event("helix_http", "put_content",
                    HELIX_OK, "File bytes stored in R2", NULL);
    return HELIX_OK;
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC: helix_http_get_clonepool
 * GET /clonepool/:hex_id — fetch content from R2
 * Caller owns *out_data and must free() it.
 * ══════════════════════════════════════════════════════════════════════════ */

helix_result_t helix_http_get_clonepool(const char* worker_url,
                                        const char* auth_token,
                                        const char* hex_id,
                                        void**  out_data,
                                        size_t* out_size) {
    char url[512];
    snprintf(url, sizeof(url), "%s/clonepool/%s", worker_url, hex_id);

    struct curl_slist* hdrs = NULL;
    http_buf_t resp = {NULL, 0};
    CURL* curl = _curl_init(url, auth_token, &hdrs, &resp);
    if (!curl) {
        helix_log_event("helix_http", "get_clonepool",
                        HELIX_ERROR_INTERNAL,
                        "curl_easy_init() failed",
                        "Check libcurl is installed and linked correctly.");
        return HELIX_ERROR_INTERNAL;
    }

    CURLcode res = curl_easy_perform(curl);
    long http_code = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    curl_slist_free_all(hdrs);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        free(resp.ptr);
        helix_log_event("helix_http", "get_clonepool",
                        HELIX_ERROR_R2_READ,
                        curl_easy_strerror(res),
                        "Check PHOENIX_WORKER_URL and network connectivity.");
        return HELIX_ERROR_R2_READ;
    }
    if (http_code == 404) {
        free(resp.ptr);
        helix_log_event("helix_http", "get_clonepool",
                        HELIX_ERROR_NOT_FOUND,
                        "hex_id not found in R2 clonepool",
                        "Run 'phoenix-intake <file>' to register it first.");
        return HELIX_ERROR_NOT_FOUND;
    }
    if (http_code < 200 || http_code >= 300) {
        free(resp.ptr);
        helix_log_event("helix_http", "get_clonepool",
                        HELIX_ERROR_R2_READ,
                        "Worker returned non-2xx status",
                        "Check Worker logs and PHOENIX_AUTH token.");
        return HELIX_ERROR_R2_READ;
    }

    *out_data = resp.ptr;   /* caller must free() */
    *out_size = resp.len;

    helix_log_event("helix_http", "get_clonepool",
                    HELIX_OK, "Content fetched from R2", NULL);
    return HELIX_OK;
}
