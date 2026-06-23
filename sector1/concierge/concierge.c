/*
 * concierge.c — Windows-side Phoenix Concierge
 * Compiled as a native Win32 executable.
 *
 * Lives on the Windows side of the WSL2 gap.
 * Receives from Phoenix Office / any Windows source.
 * Chops payload using the same PHNX chunk format as bridge.py.
 * Sends to bridge kernel at 127.0.0.1:9900.
 * Returns result to caller.
 *
 * Compile on Windows (MinGW or MSVC):
 *   gcc -o concierge.exe concierge.c -lws2_32
 *   cl concierge.c ws2_32.lib /Fe:concierge.exe
 *
 * Compile on Linux for testing (no Winsock):
 *   gcc -DLINUX_TEST -o concierge_test concierge.c
 *
 * Usage:
 *   concierge.exe                        -- server mode, port 9901
 *   concierge.exe send "hello frank"     -- one-shot send
 *   concierge.exe status                 -- ping bridge
 */

#ifdef LINUX_TEST
  #include <sys/socket.h>
  #include <netinet/in.h>
  #include <arpa/inet.h>
  #include <unistd.h>
  #define closesocket close
  #define SOCKET int
  #define INVALID_SOCKET -1
  #define SOCKET_ERROR   -1
  #define WSAStartup(a,b) 0
  #define WSACleanup()
  typedef struct { int wVersion; } WSADATA;
#else
  #include <winsock2.h>
  #include <ws2tcpip.h>
  #pragma comment(lib, "ws2_32.lib")
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

/* ── CONFIG ──────────────────────────────────────────────────────────────────*/
#define BRIDGE_HOST    "127.0.0.1"
#define BRIDGE_PORT    9900
#define CONCIERGE_PORT 9901        /* Windows-side listener */
#define CHUNK_SIZE     4096
#define MAX_PAYLOAD    (4096 * 256)
#define CHUNK_MAGIC    "PHNX"

/* ── CHUNK HEADER (matches bridge.py exactly) ────────────────────────────────*/
#pragma pack(push, 1)
typedef struct {
    char     magic[4];   /* "PHNX"          */
    uint32_t seq;        /* sequence number  */
    uint32_t total;      /* total chunks     */
    uint32_t size;       /* data bytes       */
    uint8_t  checksum[8];/* blake2b-8        */
} ChunkHeader;
#pragma pack(pop)

#define HEADER_SIZE sizeof(ChunkHeader)

/* ── PORTABLE BLAKE2B-LITE (matches helix_kernel.c) ─────────────────────────*/
static void blake2b_8(const uint8_t *data, size_t len, uint8_t out[8]) {
    uint64_t h = 0xcbf29ce484222325ULL;
    for (size_t i = 0; i < len; i++) {
        h ^= (uint64_t)data[i];
        h *= 0x00000100000001B3ULL;
        h ^= h >> 33;
        h *= 0xff51afd7ed558ccdULL;
        h ^= h >> 33;
    }
    memcpy(out, &h, 8);
}

/* ── CHUNK BUILD ─────────────────────────────────────────────────────────────*/
static uint8_t *build_chunk(uint32_t seq, uint32_t total,
                             const uint8_t *data, uint32_t size,
                             size_t *out_len)
{
    *out_len = HEADER_SIZE + size;
    uint8_t *buf = malloc(*out_len);
    if (!buf) return NULL;

    ChunkHeader *hdr = (ChunkHeader *)buf;
    memcpy(hdr->magic, CHUNK_MAGIC, 4);
    hdr->seq   = htonl(seq);
    hdr->total = htonl(total);
    hdr->size  = htonl(size);
    blake2b_8(data, size, hdr->checksum);
    memcpy(buf + HEADER_SIZE, data, size);
    return buf;
}

/* ── ENVELOPE BUILD ──────────────────────────────────────────────────────────*/
static char *build_envelope(const char *source, const char *family,
                             const char *data)
{
    /* simple JSON — no external deps */
    size_t len = strlen(data) * 2 + 256;
    char *env  = malloc(len);
    if (!env) return NULL;

    /* escape backslashes and quotes in data */
    char *esc = malloc(strlen(data) * 2 + 4);
    if (!esc) { free(env); return NULL; }
    const char *s = data;
    char *d = esc;
    while (*s) {
        if (*s == '"' || *s == '\\') *d++ = '\\';
        *d++ = *s++;
    }
    *d = '\0';

    snprintf(env, len,
             "{\"source\":\"%s\",\"family\":\"%s\",\"data\":\"%s\"}",
             source, family, esc);
    free(esc);
    return env;
}

/* ── TCP SEND/RECV ───────────────────────────────────────────────────────────*/
static int tcp_connect(const char *host, int port) {
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return -1;

    struct sockaddr_in addr = {0};
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons((uint16_t)port);
    addr.sin_addr.s_addr = inet_addr(host);

    if (connect(s, (struct sockaddr *)&addr, sizeof(addr)) == SOCKET_ERROR) {
        closesocket(s);
        return -1;
    }
    return (int)s;
}

static int tcp_send_all(int s, const uint8_t *buf, size_t len) {
    size_t sent = 0;
    while (sent < len) {
        int n = send((SOCKET)s, (const char *)buf + sent,
                     (int)(len - sent), 0);
        if (n <= 0) return -1;
        sent += (size_t)n;
    }
    return 0;
}

static char *tcp_recv_all(int s, size_t *out_len) {
    size_t cap = 65536, used = 0;
    char *buf = malloc(cap);
    if (!buf) return NULL;
    while (1) {
        if (used + 4096 > cap) {
            cap *= 2;
            char *nb = realloc(buf, cap);
            if (!nb) { free(buf); return NULL; }
            buf = nb;
        }
        int n = recv((SOCKET)s, buf + used, 4096, 0);
        if (n <= 0) break;
        used += (size_t)n;
    }
    buf[used] = '\0';
    *out_len = used;
    return buf;
}

/* ── CORE: SEND TO BRIDGE ────────────────────────────────────────────────────*/
static char *concierge_send(const char *source, const char *family,
                             const char *data)
{
    char *env = build_envelope(source, family, data);
    if (!env) return strdup("{\"ok\":false,\"error\":\"envelope alloc\"}");

    printf("[concierge] → bridge %s:%d  family=%s  %zu bytes\n",
           BRIDGE_HOST, BRIDGE_PORT, family, strlen(data));

    int s = tcp_connect(BRIDGE_HOST, BRIDGE_PORT);
    if (s < 0) {
        free(env);
        printf("[concierge] bridge unreachable — is bridge.py running in WSL2?\n");
        return strdup("{\"ok\":false,\"error\":\"bridge unreachable\"}");
    }

    tcp_send_all(s, (uint8_t *)env, strlen(env));
#ifdef _WIN32
    shutdown(s, SD_SEND);
#else
    shutdown(s, SHUT_WR);
#endif
    free(env);

    size_t resp_len = 0;
    char *resp = tcp_recv_all(s, &resp_len);
    closesocket(s);

    printf("[concierge] ← bridge  %zu bytes\n", resp_len);
    return resp ? resp : strdup("{\"ok\":false,\"error\":\"recv failed\"}");
}

/* ── SERVER MODE: listen on 9901, receive from Phoenix Office ────────────────*/
static void server_mode(void) {
    SOCKET srv = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    struct sockaddr_in addr = {0};
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons(CONCIERGE_PORT);
    addr.sin_addr.s_addr = INADDR_ANY;

    int yes = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, (char *)&yes, sizeof(yes));
    bind(srv, (struct sockaddr *)&addr, sizeof(addr));
    listen(srv, 64);

    printf("[concierge] Windows server on 0.0.0.0:%d\n", CONCIERGE_PORT);
    printf("[concierge] forwarding to bridge %s:%d\n", BRIDGE_HOST, BRIDGE_PORT);

    while (1) {
        SOCKET client = accept(srv, NULL, NULL);
        if (client == INVALID_SOCKET) continue;

        /* read request */
        char buf[MAX_PAYLOAD];
        int  n = recv(client, buf, sizeof(buf)-1, 0);
        if (n <= 0) { closesocket(client); continue; }
        buf[n] = '\0';

        /* forward to bridge */
        char *result = concierge_send("windows", "passthrough", buf);
        send(client, result, (int)strlen(result), 0);
        free(result);
        closesocket(client);
    }
    closesocket(srv);
}

/* ── STATUS PING ─────────────────────────────────────────────────────────────*/
static void ping_bridge(void) {
    char *r = concierge_send("concierge", "ping", "ping");
    printf("[concierge] bridge response: %s\n", r ? r : "(null)");
    free(r);
}

/* ── MAIN ────────────────────────────────────────────────────────────────────*/
int main(int argc, char **argv) {
    WSADATA wsa;
    WSAStartup(0x0202, &wsa);

    printf("\n  Phoenix Concierge — Windows side\n");
    printf("  bridge target: %s:%d\n\n", BRIDGE_HOST, BRIDGE_PORT);

    if (argc < 2 || strcmp(argv[1], "server") == 0) {
        server_mode();
    } else if (strcmp(argv[1], "send") == 0 && argc >= 3) {
        const char *family = argc >= 4 ? argv[3] : "message";
        char *r = concierge_send("windows-cli", family, argv[2]);
        printf("%s\n", r);
        free(r);
    } else if (strcmp(argv[1], "status") == 0) {
        ping_bridge();
    } else {
        printf("Usage:\n");
        printf("  concierge.exe                      server mode (default)\n");
        printf("  concierge.exe send \"data\" [family]  one-shot send\n");
        printf("  concierge.exe status               ping bridge\n");
    }

    WSACleanup();
    return 0;
}
