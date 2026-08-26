// Layer-2 dump at SCALE: a profile with more distinct function names than
// any fixed intern table would guess (the first self-compile run silently
// wrote empty names for every function past a 512-entry cap — 92% of the
// profile unattributed). Drives the sampler directly with synthetic
// addresses (no runtime needed: records are only swept by collections),
// then decodes the dump and requires every referenced Function to carry a
// real, correct name.
#include "../yafl.h"
#include "../prof.h"
#include "../heapprof.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CHECK(cond, msg) do { if (!(cond)) { printf("FAIL: %s\n", msg); exit(1); } } while (0)

#define MASSIF_PATH "test_heapprof3.massif"
#define PB_PATH     "test_heapprof3.massif.heap.pb.gz"

// Enough distinct names to blow through any small cap: N functions plus N
// distinct file strings.
#define N_FNS 2000
static yafl_prof_fn_t fns[N_FNS];
static char names[N_FNS][32];
static char files[N_FNS][32];

// ── the same minimal readers as test_heapprof2 ─────────────────────────────
static size_t gunzip_stored(const unsigned char* in, size_t n,
                            unsigned char* out, size_t cap) {
    CHECK(n > 18 && in[0] == 0x1f && in[1] == 0x8b && in[2] == 8, "gzip magic");
    size_t pos = 10, out_n = 0;
    for (;;) {
        unsigned hdr = in[pos];
        unsigned bfinal = hdr & 1u, btype = (hdr >> 1) & 3u;
        CHECK(btype == 0, "stored blocks only");
        pos += 1;
        unsigned len = (unsigned)in[pos] | ((unsigned)in[pos + 1] << 8);
        pos += 4;
        CHECK(out_n + len <= cap, "fits");
        memcpy(out + out_n, in + pos, len);
        out_n += len;
        pos += len;
        if (bfinal)
            break;
    }
    return out_n;
}

static uint64_t rd_varint(const unsigned char* p, size_t n, size_t* at) {
    uint64_t v = 0;
    int shift = 0;
    while (*at < n) {
        unsigned char b = p[(*at)++];
        v |= (uint64_t)(b & 0x7f) << shift;
        if (!(b & 0x80))
            return v;
        shift += 7;
    }
    CHECK(0, "varint truncated");
    return 0;
}

static void rd_field(const unsigned char* p, size_t n, size_t* at,
                     unsigned wire, size_t* off, size_t* len) {
    if (wire == 0) { rd_varint(p, n, at); return; }
    CHECK(wire == 2, "wire type");
    uint64_t l = rd_varint(p, n, at);
    if (off) { *off = *at; *len = (size_t)l; }
    *at += (size_t)l;
    CHECK(*at <= n, "bounds");
}

int main(void) {
    for (int i = 0; i < N_FNS; i++) {
        snprintf(names[i], sizeof names[i], "scale::fn%05d", i);
        snprintf(files[i], sizeof files[i], "scale_%04d.yafl", i / 2);
        fns[i] = (yafl_prof_fn_t){ names[i], files[i], i + 1 };
    }
    setenv("YAFL_HEAPPROF", MASSIF_PATH, 1);
    setenv("YAFL_HEAPPROF_SAMPLE", "64", 1);
    setenv("YAFL_PROF_HZ", "0", 1);
    unlink(MASSIF_PATH);
    unlink(PB_PATH);
    yafl_prof_init(fns, N_FNS);
    yafl_prof_thread_init();
    yafl_heapprof_init();
    CHECK(yafl_heapprof_sample_enabled, "layer 2 enabled");

    // One sampled record per function, each under its own single-frame
    // stack. Synthetic slot-aligned addresses: no collection ever runs
    // here, so nothing dereferences them.
    for (int i = 0; i < N_FNS; i++) {
        yafl_prof_enter((uint32_t)i);
        yafl_heapprof_sample_alloc((void*)(uintptr_t)(0x100000 + i * 4096), 128, 64);
        yafl_prof_leave();
    }
    size_t bytes = 0;
    CHECK(yafl_heapprof_sample_records(&bytes) == N_FNS, "every alloc sampled");

    // Stack DIVERSITY at compiler scale: deep recursive stacks whose
    // differentiating frames sit far above the leaf. Uncapped hash-consing
    // exhausts any pool on this shape (the self-compile lost 13k records'
    // stacks); the deepest-window cap collapses it to a handful of unique
    // stacks and must lose NOTHING.
    #define DIVERSE 50000
    #define TAIL    500
    for (int i = 0; i < DIVERSE; i++) {
        yafl_prof_enter((uint32_t)(i % N_FNS));            // differentiator
        yafl_prof_enter((uint32_t)((i * 7) % N_FNS));      // second differentiator
        for (int d = 0; d < TAIL; d++)
            yafl_prof_enter(0);                            // the recursion tail
        yafl_heapprof_sample_alloc((void*)(uintptr_t)(0x40000000 + (uintptr_t)i * 4096),
                                   128, 64);
        for (int d = 0; d < TAIL + 2; d++)
            yafl_prof_leave();
    }
    yafl_heapprof_dump();

    FILE* f = fopen(PB_PATH, "rb");
    CHECK(f != NULL, "pprof file exists");
    static unsigned char gz[8 << 20], pb[8 << 20];
    size_t gz_n = fread(gz, 1, sizeof gz, f);
    fclose(f);
    size_t pb_n = gunzip_stored(gz, gz_n, pb, sizeof pb);

    // Decode: string table + every Function's name/file indices.
    static const unsigned char* strv[3 * N_FNS + 64];
    static size_t strl[3 * N_FNS + 64];
    unsigned n_strs = 0;
    unsigned fn_count = 0, fn_named = 0;
    uint64_t total_objects = 0;
    size_t at = 0;
    while (at < pb_n) {
        uint64_t tag = rd_varint(pb, pb_n, &at);
        unsigned fieldno = (unsigned)(tag >> 3), wire = (unsigned)(tag & 7);
        size_t off = 0, len = 0;
        rd_field(pb, pb_n, &at, wire, &off, &len);
        if (fieldno == 6 && n_strs < 3 * N_FNS + 64) {
            strv[n_strs] = pb + off;
            strl[n_strs] = len;
            n_strs++;
        } else if (fieldno == 2) {                        // sample
            size_t sat = off, send = off + len;
            while (sat < send) {
                uint64_t stag = rd_varint(pb, send, &sat);
                unsigned sno = (unsigned)(stag >> 3), sw = (unsigned)(stag & 7);
                size_t poff = 0, plen = 0;
                rd_field(pb, send, &sat, sw, &poff, &plen);
                if (sno == 2 && sw == 2) {                // packed values
                    size_t pat = poff;
                    uint64_t objs = rd_varint(pb, poff + plen, &pat);
                    total_objects += objs;
                }
            }
        } else if (fieldno == 5) {
            size_t fat = off, fend = off + len;
            uint64_t name = 0, file = 0;
            while (fat < fend) {
                uint64_t ftag = rd_varint(pb, fend, &fat);
                unsigned fno = (unsigned)(ftag >> 3), fw = (unsigned)(ftag & 7);
                if (fno == 2 && fw == 0)      name = rd_varint(pb, fend, &fat);
                else if (fno == 4 && fw == 0) file = rd_varint(pb, fend, &fat);
                else rd_field(pb, fend, &fat, fw, NULL, NULL);
            }
            fn_count++;
            if (name != 0 && file != 0)
                fn_named++;
        }
    }
    // +1: the (truncated) pseudo-function the capped deep stacks root at.
    CHECK(fn_count == N_FNS + 1, "every used frame got a Function record");
    CHECK(fn_named == N_FNS + 1, "every Function carries a real name AND file");

    // No stack was lost: every sampled record appears in some sample, so
    // the summed inuse_objects covers all of them (each weighted >= 1 by
    // the estimator; a lost stack is EXCLUDED from samples and shows up
    // as a shortfall here).
    CHECK(total_objects >= N_FNS + DIVERSE,
          "diversity storm lost no stacks (deepest-window cap)");

    // Spot-check content: the last registered name must appear verbatim in
    // the string table (the first casualties of a capped intern table are
    // the late names).
    bool found_last = false;
    for (unsigned i = 0; i < n_strs; i++)
        if (strl[i] == strlen(names[N_FNS - 1])
            && memcmp(strv[i], names[N_FNS - 1], strl[i]) == 0)
            found_last = true;
    CHECK(found_last, "late-interned names present verbatim");

    unlink(MASSIF_PATH);
    unlink(PB_PATH);
    printf("OK\n");
    return 0;
}
