/*
 * baseline.c — plain malloc/memcpy, no Helix tiers
 * Same workloads so the comparison is apples to apples.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

#define BLOCK_SIZE 4096

static double now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec*1000.0+t.tv_nsec/1e6;}
static void fill_random(uint8_t*b,size_t n,uint64_t s){for(size_t i=0;i<n;i++){s^=s<<13;s^=s>>7;s^=s<<17;b[i]=(uint8_t)(s&0xFF);}}

static void transform(const uint8_t*src,uint8_t*dst,size_t n){
    for(size_t i=0;i<n;i++){uint8_t b=src[i];b^=(uint8_t)(i&0xFF);b=(b<<3)|(b>>5);b^=(uint8_t)(n&0xFF);dst[i]=b;}
}

int main(void){
    printf("\n  Baseline (no Helix) — same transforms, flat malloc\n");
    printf("  %-28s %10s  %9s\n","Benchmark","Time","Throughput");
    printf("  %s\n","────────────────────────────────────────────────");

    /* Sequential */
    {
        size_t N=32*1024*1024; uint8_t*s=malloc(N),*d=malloc(N);
        fill_random(s,N,0xDEADBEEF);
        double t0=now_ms();
        for(size_t off=0;off+BLOCK_SIZE<=N;off+=BLOCK_SIZE) transform(s+off,d+off,BLOCK_SIZE);
        double el=now_ms()-t0;
        printf("  %-28s %8.1f ms  %7.0f MB/s\n","Sequential 32MB",el,(N/1024.0/1024.0)/(el/1000.0));
        free(s);free(d);
    }
    /* Random */
    {
        size_t POOL=1*1024*1024; uint8_t*s=malloc(POOL),*d=malloc(512);
        fill_random(s,POOL,0xCAFEBABE);
        uint64_t rng=0x12345678; size_t total=0;
        double t0=now_ms();
        for(int i=0;i<100000;i++){
            rng=rng*6364136223846793005ULL+1442695040888963407ULL;
            size_t off=(rng>>33)%(POOL-256); size_t sz=64+((rng>>17)&0xFF);
            transform(s+off,d,sz); total+=sz;
        }
        double el=now_ms()-t0;
        printf("  %-28s %8.1f ms  %7.0f MB/s\n","Random access 100k ops",el,(total/1024.0/1024.0)/(el/1000.0));
        free(s);free(d);
    }
    /* Checksum */
    {
        size_t N=64*1024*1024; uint8_t*b=malloc(N);
        fill_random(b,N,0xABCDEF01);
        double t0=now_ms(); volatile uint64_t h=0; size_t ops=0;
        for(size_t off=0;off+65536<=N;off+=65536){
            uint64_t x=0xcbf29ce484222325ULL;
            for(size_t i=0;i<65536;i++){x^=b[off+i];x*=0x00000100000001B3ULL;x^=x>>33;x*=0xff51afd7ed558ccdULL;x^=x>>33;}
            h^=x; ops++;
        }
        double el=now_ms()-t0; (void)h;
        printf("  %-28s %8.1f ms  %7.0f MB/s\n","Checksum 64MB",el,(N/1024.0/1024.0)/(el/1000.0));
        free(b);
    }
    printf("\n");
    return 0;
}
