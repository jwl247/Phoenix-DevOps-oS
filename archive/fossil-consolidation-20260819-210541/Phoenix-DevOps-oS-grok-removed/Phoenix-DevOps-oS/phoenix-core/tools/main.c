/*
 * tools/main.c — phoenix-intake CLI entry point
 * Phoenix DevOps OS / Lost Ark
 *
 * Usage:
 *   phoenix-intake <file> [category] [label]
 *   phoenix-intake --resolve <hex_id_or_name>
 *   phoenix-intake --version
 *
 * Routes to helix_ingress_intake() or helix_egress_resolve()
 */

#include "../include/helix.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define VERSION "0.1.0"

static void print_usage(void) {
    printf("phoenix-intake v%s — Phoenix DevOps OS / Lost Ark\n\n", VERSION);
    printf("Usage:\n");
    printf("  phoenix-intake <file> [category] [label]   intake a file\n");
    printf("  phoenix-intake --resolve <hex_id>          resolve by hex ID\n");
    printf("  phoenix-intake --version                   show version\n");
    printf("  phoenix-intake --help                      this message\n\n");
    printf("Environment:\n");
    printf("  PHOENIX_WORKER_URL   Cloudflare Worker URL (for R2 + D1 sync)\n");
    printf("  PHOENIX_AUTH         Auth token  (Authorization: Bearer header)\n");
    printf("  PHOENIX_CACHE        Local cache directory\n\n");
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        print_usage();
        return 1;
    }

    if (strcmp(argv[1], "--version") == 0) {
        printf("phoenix-intake v%s\n", VERSION);
        return 0;
    }

    if (strcmp(argv[1], "--help") == 0) {
        print_usage();
        return 0;
    }

    if (strcmp(argv[1], "--resolve") == 0) {
        if (argc < 3) {
            fprintf(stderr, "Usage: phoenix-intake --resolve <hex_id>\n");
            return 1;
        }
        void* data = NULL;
        size_t size = 0;
        helix_result_t r = helix_egress_resolve(argv[2], &data, &size);
        if (r == HELIX_OK && data) {
            printf("%.*s\n", (int)size, (char*)data);
            free(data);
            return 0;
        }
        return 1;
    }

    /* Default: intake */
    const char* file_path = argv[1];
    const char* category  = (argc >= 3) ? argv[2] : NULL;
    const char* label     = (argc >= 4) ? argv[3] : NULL;

    helix_result_t r = helix_ingress_intake(file_path, category, label);
    return (r == HELIX_OK) ? 0 : 1;
}
