/*
 * helix_diagnostics.c — Automatic journaling for Phoenix Helix C-Core
 * Phoenix DevOps OS / Lost Ark
 *
 * Every event posts: What happened + Why + Recommended Action.
 * This is a non-negotiable design rule — never swallow errors silently.
 */

#include "../include/helix.h"
#include <stdio.h>
#include <string.h>

static helix_diagnostic_t last_diag = {0};

void helix_post_diagnostic(const helix_diagnostic_t* diag) {
    if (!diag) return;
    last_diag = *diag;

    /* Always print to stderr so it appears even when stdout is redirected */
    fprintf(stderr, "\n[HELIX] %s :: %s\n",
            diag->component ? diag->component : "?",
            diag->operation ? diag->operation : "?");

    const char* result_str = "UNKNOWN";
    switch (diag->result) {
        case HELIX_OK:                  result_str = "OK";            break;
        case HELIX_ERROR_GENERIC:       result_str = "ERROR";         break;
        case HELIX_ERROR_INVALID_ARG:   result_str = "INVALID_ARG";   break;
        case HELIX_ERROR_HEX_COLLISION: result_str = "HEX_COLLISION"; break;
        case HELIX_ERROR_R2_WRITE:      result_str = "R2_WRITE_FAIL"; break;
        case HELIX_ERROR_R2_READ:       result_str = "R2_READ_FAIL";  break;
        case HELIX_ERROR_D1_WRITE:      result_str = "D1_WRITE_FAIL"; break;
        case HELIX_ERROR_NOT_FOUND:     result_str = "NOT_FOUND";     break;
        case HELIX_ERROR_IO:            result_str = "IO_ERROR";      break;
        case HELIX_ERROR_OOM:           result_str = "OUT_OF_MEMORY"; break;
        case HELIX_ERROR_INTERNAL:      result_str = "INTERNAL";      break;
    }
    fprintf(stderr, "  Result : %s (%d)\n", result_str, (int)diag->result);

    if (diag->reason)
        fprintf(stderr, "  Reason : %s\n", diag->reason);
    if (diag->recommended_action)
        fprintf(stderr, "  Action : %s\n", diag->recommended_action);
    fprintf(stderr, "\n");
    fflush(stderr);
}

void helix_log_event(const char* component, const char* operation,
                     helix_result_t result, const char* reason,
                     const char* recommended_action) {
    helix_diagnostic_t d = {
        .component          = component,
        .operation          = operation,
        .result             = result,
        .reason             = reason,
        .recommended_action = recommended_action
    };
    helix_post_diagnostic(&d);
}

const helix_diagnostic_t* helix_get_last_diagnostic(void) {
    return &last_diag;
}
