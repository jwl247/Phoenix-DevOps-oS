#ifndef HELIX_HTTP_H
#define HELIX_HTTP_H

#include "helix.h"

/*
 * helix_http.h — Internal HTTP layer for Phoenix Helix C-Core
 * Phoenix DevOps OS / Lost Ark
 *
 * Called by helix_ingress and helix_egress. Requires libcurl at link time.
 *
 * Endpoints (relative to PHOENIX_WORKER_URL):
 *   POST /clonepool          — register metadata in D1 glossary
 *   PUT  /clonepool/:hex_id  — store file bytes in R2
 *   POST /custody            — append event to D1 custody ledger (append-only)
 *   GET  /clonepool/:hex_id  — fetch content from R2
 */

helix_result_t helix_http_post_clonepool(const char* worker_url,
                                         const char* auth_token,
                                         const helix_sidecar_t* s);

helix_result_t helix_http_post_custody(const char* worker_url,
                                       const char* auth_token,
                                       const helix_sidecar_t* s);

helix_result_t helix_http_put_content(const char* worker_url,
                                      const char* auth_token,
                                      const char* hex_id,
                                      const void* data,
                                      size_t      data_len);

helix_result_t helix_http_get_clonepool(const char* worker_url,
                                        const char* auth_token,
                                        const char* hex_id,
                                        void**  out_data,
                                        size_t* out_size);

#endif /* HELIX_HTTP_H */
