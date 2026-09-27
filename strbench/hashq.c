// Hash quality on real keys: every distinct token (<=15 bytes, inline) in the
// self-compile stream, hashed by (a) the inline fast path in yafl.h and
// (b) the byte-stream function str_hash_heap uses. Reports 31-bit collisions
// and how evenly the low 5 bits (a HAMT level) spread.
#include "yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
static uint32_t stream_hash(const uint8_t* p, int n) {
    uint64_t h = STR_HASH_SEED ^ (uint64_t)n; int i = 0;
    for (; i + 8 <= n; i += 8) h = str_hash_mix(h, str_load_le64(p + i));
    uint64_t acc = 0; for (int k = 0; i < n; i++, k++) acc |= (uint64_t)p[i] << (8 * k);
    if (n % 8) h = str_hash_mix(h, acc);
    return (uint32_t)str_hash_finish(h);
}
static int cmps(const void* a, const void* b) { return strcmp(*(char* const*)a, *(char* const*)b); }
static int cmpu(const void* a, const void* b) { uint32_t x = *(uint32_t*)a, y = *(uint32_t*)b; return x < y ? -1 : x > y; }
int main(int argc, char** argv) {
    FILE* f = fopen(argv[1], "rb"); fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    char* t = malloc(n + 1); fread(t, 1, n, f); t[n] = 0;
    // distinct identifier-ish tokens of length 1..15
    int cap = 1 << 20, m = 0; char** toks = malloc(cap * sizeof *toks);
    for (long i = 0; i < n; ) {
        if (isalnum((unsigned char)t[i]) || t[i] == '_' || t[i] == ':') {
            long j = i; while (j < n && (isalnum((unsigned char)t[j]) || t[j] == '_' || t[j] == ':')) j++;
            if (j - i <= 15 && m < cap) { toks[m] = strndup(t + i, j - i); m++; }
            i = j;
        } else i++;
    }
    qsort(toks, m, sizeof *toks, cmps);
    int d = 0; for (int i = 0; i < m; i++) if (i == 0 || strcmp(toks[i], toks[i-1])) toks[d++] = toks[i];
    uint32_t* ha = malloc(d * 4); uint32_t* hb = malloc(d * 4);
    int bucketsA[32] = {0}, bucketsB[32] = {0};
    for (int i = 0; i < d; i++) {
        str_t s = str_from_bytes((const uint8_t*)toks[i], (int32_t)strlen(toks[i]));
        ha[i] = (uint32_t)str_hash(s);
        hb[i] = stream_hash((const uint8_t*)toks[i], (int)strlen(toks[i]));
        bucketsA[ha[i] & 31]++; bucketsB[hb[i] & 31]++;
    }
    qsort(ha, d, 4, cmpu); qsort(hb, d, 4, cmpu);
    int ca = 0, cb = 0; for (int i = 1; i < d; i++) { ca += ha[i] == ha[i-1]; cb += hb[i] == hb[i-1]; }
    int minA = d, maxA = 0, minB = d, maxB = 0;
    for (int i = 0; i < 32; i++) { if (bucketsA[i] < minA) minA = bucketsA[i]; if (bucketsA[i] > maxA) maxA = bucketsA[i];
                                   if (bucketsB[i] < minB) minB = bucketsB[i]; if (bucketsB[i] > maxB) maxB = bucketsB[i]; }
    printf("distinct inline tokens: %d\n", d);
    printf("inline fast path : 31-bit collisions %d, low-5-bit buckets min %d max %d\n", ca, minA, maxA);
    printf("stream function  : 31-bit collisions %d, low-5-bit buckets min %d max %d\n", cb, minB, maxB);
    return 0;
}
