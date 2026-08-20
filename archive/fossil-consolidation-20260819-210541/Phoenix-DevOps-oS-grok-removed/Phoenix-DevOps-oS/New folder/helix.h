#ifndef HELIX_H
#define HELIX_H

#include <stdint.h>
#include <stddef.h>

/*
 * Helix-C Public API
 * Double Helix implementation for Lost Ark (Phoenix DevOps OS)
 *
 * Design Principles:
 * - Horseshoe / daisy chain flow in core paths
 * - Fail fast with rich diagnostics
 * - Automatic journaling: What + Why + Recommended Action
 * - Designed for integration with existing Suit + Frank layer
 */

// ============================================================================
// TYPES
// ============================================================================

typedef enum {
    HELIX_OK = 0,
    HELIX_ERROR_GENERIC,
    HELIX_ERROR_INVALID_ARG,
    HELIX_ERROR_HEX_COLLISION,
    HELIX_ERROR_R2_WRITE_FAILED,
    HELIX_ERROR_R2_READ_FAILED,
    HELIX_ERROR_D1_WRITE_FAILED,
    HELIX_ERROR_NOT_FOUND,
    HELIX_ERROR_INTERNAL
} helix_result_t;

typedef struct {
    const char* component;      // e.g. "helix_ingress", "helix_egress"
    const char* operation;      // e.g. "hex_generation", "r2_write"
    helix_result_t result;
    const char* reason;         // Specific reason for failure or event.
    const char* recommended_action; // Suggested next step
} helix_diagnostic_t;

// ============================================================================
// DIAGNOSTIC / JOURNALING API (Core requirement)
// ============================================================================

// Post a diagnostic event to screen/journal automatically
void helix_post_diagnostic(const helix_diagnostic_t* diag);

// Simple helper for common cases
void helix_log_event(const char* component, const char* operation, 
                     helix_result_t result, const char* reason, 
                     const char* recommended_action);

// ============================================================================
// INGRESS (Write Path) - Horseshoe flow
// ============================================================================

helix_result_t helix_ingress_intake(const char* file_path, 
                                    const char* category, 
                                    const char* label);

// ============================================================================
// EGRESS (Read / Resolution Path) - Horseshoe flow
// ============================================================================

helix_result_t helix_egress_resolve(const char* identifier, 
                                    void** output_data, 
                                    size_t* output_size);

// ============================================================================
// UTILITIES
// ============================================================================

// Generate deterministic hex ID
const char* helix_generate_hex_id(const char* input);

// Get last diagnostic for inspection
const helix_diagnostic_t* helix_get_last_diagnostic(void);

#endif // HELIX_H
