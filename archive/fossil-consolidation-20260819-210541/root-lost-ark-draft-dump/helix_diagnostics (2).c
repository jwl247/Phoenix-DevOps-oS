#include "helix.h"
#include <stdio.h>
#include <string.h>

static helix_diagnostic_t last_diagnostic = {0};

void helix_post_diagnostic(const helix_diagnostic_t* diag) {
    if (!diag) return;

    // Store for later inspection
    last_diagnostic = *diag;

    // Automatic journal post to screen (core requirement)
    printf("\n[HELIX] %s :: %s\n", diag->component, diag->operation);
    printf("  Result: %d\n", diag->result);
    if (diag->reason) {
        printf("  Reason: %s\n", diag->reason);
    }
    if (diag->recommended_action) {
        printf("  Recommended Action: %s\n", diag->recommended_action);
    }
    printf("\n");
}

void helix_log_event(const char* component, const char* operation, 
                     helix_result_t result, const char* reason, 
                     const char* recommended_action) {
    
    helix_diagnostic_t diag = {
        .component = component,
        .operation = operation,
        .result = result,
        .reason = reason,
        .recommended_action = recommended_action
    };

    helix_post_diagnostic(&diag);
}

const helix_diagnostic_t* helix_get_last_diagnostic(void) {
    return &last_diagnostic;
}
