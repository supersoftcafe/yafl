// Heap profiling layer 2 (heapprof.c): allocation-site sampling at the
// slow path, record survival across collections, compaction forwarding
// maintenance, and the pprof inuse_space dump.
//
// What these tests pin down, against the REAL runtime (thread_start, real
// collections forced by gc_debug_major_now):
//
//   * before init, every layer-2 entry point is a no-op;
//   * with YAFL_HEAPPROF_SAMPLE=1 every slow-path acquisition samples, so
//     multi-page allocations are recorded deterministically;
//   * records DROP when their object dies: a major collection's prune
//     rewrites the objects bitmap to the live set and the sweep reads it;
//   * records SURVIVE compaction: survivors' records are re-keyed through
//     the published forward word, never dropped with the evacuated page;
//   * the .heap.pb.gz dump is a gzip stream (stored-block deflate) whose
//     protobuf carries inuse_objects/inuse_space, the sampling site's
//     function names from the --profile descriptors, and per-site byte
//     totals consistent with the live record set.
#include "../yafl.h"
#include "../heapprof.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CHECK(cond, msg) do { if (!(cond)) { printf("FAIL: %s\n", msg); exit(1); } } while (0)

#define MASSIF_PATH "test_heapprof2.massif"
#define PB_PATH     "test_heapprof2.massif.heap.pb.gz"

enum { FN_KEEPER = 0, FN_CHURN = 1, FN_COUNT = 2 };
static const yafl_prof_fn_t TEST_FNS[FN_COUNT] = {
    { "test::keeper", "test_heapprof2.yafl", 10 },
    { "test::churn",  "test_heapprof2.yafl", 20 },
};

// Multi-page: > MAX_OBJECT_SIZE (a page's slot region), so every one goes
// through the dedicated-run arm of the slow path and MUST be sampled at
// rate 1. 100 KiB ~= 7 pages of 16 KiB.
#define BIG_LEN   (100 * 1024)
#define KEEP_BIG  4
#define DROP_BIG  4

// Small churn: enough 200-byte strings to cross many page refills; 63/64
// die, leaving the survivors' pages sparse enough for compaction to pick
// them up on the following majors.
#define SMALL_N     2048
#define SMALL_LEN   200
#define SMALL_KEEP  64          // keep every 64th

static object_t* keep_big[KEEP_BIG];
static object_t* drop_big[DROP_BIG];
static object_t* keep_small[SMALL_N / SMALL_KEEP];

static roots_declaration_func_t _prev_roots;
static void _declare_roots(void (*declare)(object_t**)) {
    _prev_roots(declare);
    for (int i = 0; i < KEEP_BIG; i++) declare(&keep_big[i]);
    for (int i = 0; i < DROP_BIG; i++) declare(&drop_big[i]);
    for (int i = 0; i < SMALL_N / SMALL_KEEP; i++) declare(&keep_small[i]);
}

// Allocations happen in NOINLINE helpers so their frames (and any register
// copies of dropped pointers) are gone before the killing majors run.
static __attribute__((noinline)) void alloc_bigs(void) {
    for (int i = 0; i < KEEP_BIG; i++) keep_big[i] = string_allocate(BIG_LEN);
    for (int i = 0; i < DROP_BIG; i++) drop_big[i] = string_allocate(BIG_LEN);
}

static __attribute__((noinline)) void churn_smalls(void) {
    for (int i = 0; i < SMALL_N; i++) {
        object_t* s = string_allocate(SMALL_LEN);
        if (i % SMALL_KEEP == 0)
            keep_small[i / SMALL_KEEP] = s;
    }
}

// Scrub argument/return registers of stale heap pointers.
static __attribute__((noinline)) object_t* scrub(void) {
    return string_allocate(8);
}

// gc_debug_major_now is ONE incremental FSA step with a major requested.
// Drive whole collections by stepping until the live record set holds
// still across a full window of steps (several complete cycles at test
// scale), bounded so a broken sweep fails instead of spinning.
static size_t settle(void) {
    size_t prev = (size_t)-1, prev_n = 0;
    for (int window = 0; window < 200; window++) {
        for (int i = 0; i < 5000; i++)
            gc_debug_major_now(NULL);
        size_t bytes = 0, n = yafl_heapprof_sample_records(&bytes);
        if (bytes == prev && n == prev_n)
            return bytes;
        prev = bytes;
        prev_n = n;
    }
    CHECK(0, "record set settles under repeated majors");
    return 0;
}

static size_t step_majors(int steps) {
    for (int i = 0; i < steps; i++)
        gc_debug_major_now(NULL);
    size_t bytes = 0;
    yafl_heapprof_sample_records(&bytes);
    return bytes;
}

// ── minimal gzip (stored-block deflate) reader ─────────────────────────────
static size_t gunzip_stored(const unsigned char* in, size_t n,
                            unsigned char* out, size_t cap) {
    CHECK(n > 18 && in[0] == 0x1f && in[1] == 0x8b && in[2] == 8,
          "gzip magic + deflate method");
    CHECK(in[3] == 0, "no gzip optional fields");
    size_t pos = 10, out_n = 0;   // fixed header
    unsigned bit = 0;
    for (;;) {
        unsigned hdr = (unsigned)(in[pos] >> bit);
        unsigned bfinal = hdr & 1u, btype = (hdr >> 1) & 3u;
        CHECK(btype == 0, "stored deflate blocks only");
        pos += 1;                  // skip to the byte boundary past 3 bits
        bit = 0;
        unsigned len = (unsigned)in[pos] | ((unsigned)in[pos + 1] << 8);
        unsigned nlen = (unsigned)in[pos + 2] | ((unsigned)in[pos + 3] << 8);
        CHECK((len ^ nlen) == 0xffffu, "stored block LEN/NLEN");
        pos += 4;
        CHECK(out_n + len <= cap, "decompressed fits");
        memcpy(out + out_n, in + pos, len);
        out_n += len;
        pos += len;
        if (bfinal)
            break;
    }
    unsigned long isize = (unsigned long)in[n - 4] | ((unsigned long)in[n - 3] << 8)
                        | ((unsigned long)in[n - 2] << 16) | ((unsigned long)in[n - 1] << 24);
    CHECK(isize == (out_n & 0xfffffffful), "gzip ISIZE trailer");
    return out_n;
}

// ── minimal profile.proto reader ───────────────────────────────────────────
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

// Skip one field of the given wire type; returns payload {off,len} for
// wire type 2.
static void rd_field(const unsigned char* p, size_t n, size_t* at,
                     unsigned wire, size_t* off, size_t* len) {
    if (wire == 0) { rd_varint(p, n, at); return; }
    CHECK(wire == 2, "only varint and length-delimited fields expected");
    uint64_t l = rd_varint(p, n, at);
    if (off) { *off = *at; *len = (size_t)l; }
    *at += (size_t)l;
    CHECK(*at <= n, "field length in bounds");
}

#define MAX_STRS 256
#define MAX_IDS  4096
static const unsigned char* strs[MAX_STRS];
static size_t str_len[MAX_STRS];
static unsigned n_strs = 0;
static uint64_t fn_name_idx[MAX_IDS];      // function id -> string index
static uint64_t loc_fn_id[MAX_IDS];        // location id -> function id

static bool str_is(uint64_t idx, const char* want) {
    return idx < n_strs && strlen(want) == str_len[idx]
        && memcmp(strs[idx], want, str_len[idx]) == 0;
}

static void _entrypoint(object_t* self, fun_t continuation);

int main(void) {
    // Before any init: layer-2 entry points are no-ops.
    char dummy[64];
    yafl_heapprof_sample_alloc(dummy, 64, 64);
    yafl_heapprof_sample_forwarded(dummy, dummy + 8);
    yafl_heapprof_sample_sweep();
    size_t b0 = 0;
    CHECK(yafl_heapprof_sample_records(&b0) == 0 && b0 == 0,
          "no records before init");

    setenv("YAFL_HEAPPROF", MASSIF_PATH, 1);
    setenv("YAFL_HEAPPROF_SAMPLE", "1", 1);
    setenv("YAFL_PROF_HZ", "0", 1);        // counters/stacks only, no timers
    unlink(MASSIF_PATH);
    unlink(PB_PATH);
    yafl_prof_init(TEST_FNS, FN_COUNT);
    _prev_roots = add_roots_declaration_func(_declare_roots);

    thread_start(_entrypoint);
    return 0;
}

static void _entrypoint(object_t* self, fun_t continuation) {
    (void)self; (void)continuation;
    // gc_start (which runs yafl_heapprof_init) is called by the LAST worker
    // to register — worker 0 may reach the entry first under load. The
    // runtime is indifferent (sampling just starts a hair late); the test
    // must wait for init before asserting on it.
    for (int i = 0; i < 10000 && !yafl_heapprof_sample_enabled; i++)
        usleep(1000);
    CHECK(yafl_heapprof_sample_enabled, "layer 2 enabled by the env pair");

    // Phase 1: multi-page allocations under a known frame — all sampled.
    yafl_prof_enter(FN_KEEPER);
    alloc_bigs();
    size_t bytes0 = 0, n0 = yafl_heapprof_sample_records(&bytes0);
    CHECK(n0 >= KEEP_BIG + DROP_BIG, "every multi-page allocation sampled");
    CHECK(bytes0 >= (size_t)(KEEP_BIG + DROP_BIG) * BIG_LEN,
          "sampled bytes cover the big allocations");

    // Phase 2: death. Records for the dropped bigs go when a major's prune
    // publishes the live set.
    for (int i = 0; i < DROP_BIG; i++) drop_big[i] = NULL;
    keep_big[0] = scrub();          // also replaces one keeper with a small
    keep_big[0] = string_allocate(BIG_LEN);
    size_t bytes1 = settle();
    CHECK(bytes1 < bytes0, "dead sampled objects dropped by the major sweep");
    CHECK(bytes1 >= (size_t)KEEP_BIG * BIG_LEN, "live keepers retained");
    yafl_prof_leave();

    // Phase 3: small churn under a second frame, then compaction-heavy
    // majors. Survivor records must ride the forward words, not die with
    // the evacuated pages.
    yafl_prof_enter(FN_CHURN);
    churn_smalls();
    yafl_prof_leave();
    size_t bytes2 = settle();
    // Stable live set from here: further compaction-heavy majors must not
    // lose a single surviving record to a mis-keyed forward.
    size_t bytes3 = step_majors(20000);
    size_t check_bytes = 0;
    CHECK(yafl_heapprof_sample_records(&check_bytes) > 0, "records survive");
    CHECK(bytes3 == bytes2,
          "survivor records survive compaction (forward re-keying)");

    // Phase 4: the dump.
    yafl_heapprof_dump();

    FILE* f = fopen(PB_PATH, "rb");
    CHECK(f != NULL, "pprof file exists");
    static unsigned char gz[1 << 20], pb[1 << 20];
    size_t gz_n = fread(gz, 1, sizeof gz, f);
    fclose(f);
    size_t pb_n = gunzip_stored(gz, gz_n, pb, sizeof pb);

    // Pass A: string table, functions, locations.
    size_t at = 0;
    while (at < pb_n) {
        uint64_t tag = rd_varint(pb, pb_n, &at);
        unsigned fieldno = (unsigned)(tag >> 3), wire = (unsigned)(tag & 7);
        size_t off = 0, len = 0;
        rd_field(pb, pb_n, &at, wire, &off, &len);
        if (fieldno == 6 && n_strs < MAX_STRS) {          // string_table
            strs[n_strs] = pb + off;
            str_len[n_strs] = len;
            n_strs++;
        } else if (fieldno == 5) {                        // function
            size_t fat = off, fend = off + len;
            uint64_t id = 0, name = 0;
            while (fat < fend) {
                uint64_t ftag = rd_varint(pb, fend, &fat);
                unsigned fno = (unsigned)(ftag >> 3), fw = (unsigned)(ftag & 7);
                if (fno == 1 && fw == 0)      id = rd_varint(pb, fend, &fat);
                else if (fno == 2 && fw == 0) name = rd_varint(pb, fend, &fat);
                else rd_field(pb, fend, &fat, fw, NULL, NULL);
            }
            CHECK(id < MAX_IDS, "function id in range");
            fn_name_idx[id] = name;
        } else if (fieldno == 4) {                        // location
            size_t lat = off, lend = off + len;
            uint64_t id = 0, fn = 0;
            while (lat < lend) {
                uint64_t ltag = rd_varint(pb, lend, &lat);
                unsigned lno = (unsigned)(ltag >> 3), lw = (unsigned)(ltag & 7);
                if (lno == 1 && lw == 0) id = rd_varint(pb, lend, &lat);
                else if (lno == 4 && lw == 2) {           // line
                    size_t loff = 0, llen = 0;
                    rd_field(pb, lend, &lat, lw, &loff, &llen);
                    size_t nat = loff, nend = loff + llen;
                    while (nat < nend) {
                        uint64_t ntag = rd_varint(pb, nend, &nat);
                        unsigned nno = (unsigned)(ntag >> 3), nw = (unsigned)(ntag & 7);
                        if (nno == 1 && nw == 0) fn = rd_varint(pb, nend, &nat);
                        else rd_field(pb, nend, &nat, nw, NULL, NULL);
                    }
                } else rd_field(pb, lend, &lat, lw, NULL, NULL);
            }
            CHECK(id < MAX_IDS, "location id in range");
            loc_fn_id[id] = fn;
        }
    }
    CHECK(n_strs > 0 && str_len[0] == 0, "string table starts with empty");
    bool have_objects = false, have_space = false;
    for (unsigned i = 0; i < n_strs; i++) {
        if (str_is(i, "inuse_objects")) have_objects = true;
        if (str_is(i, "inuse_space"))  have_space = true;
    }
    CHECK(have_objects && have_space, "inuse sample types present");

    // Pass B: samples — per-site byte totals.
    uint64_t total_bytes = 0, keeper_bytes = 0, churn_bytes = 0;
    at = 0;
    while (at < pb_n) {
        uint64_t tag = rd_varint(pb, pb_n, &at);
        unsigned fieldno = (unsigned)(tag >> 3), wire = (unsigned)(tag & 7);
        size_t off = 0, len = 0;
        rd_field(pb, pb_n, &at, wire, &off, &len);
        if (fieldno != 2)
            continue;                                     // sample
        size_t sat = off, send = off + len;
        uint64_t vals[4];
        unsigned n_vals = 0;
        bool keeper = false, churn = false;
        while (sat < send) {
            uint64_t stag = rd_varint(pb, send, &sat);
            unsigned sno = (unsigned)(stag >> 3), sw = (unsigned)(stag & 7);
            size_t poff = 0, plen = 0;
            rd_field(pb, send, &sat, sw, &poff, &plen);
            if (sno == 1 && sw == 2) {                    // packed location ids
                size_t pat = poff, pend = poff + plen;
                while (pat < pend) {
                    uint64_t lid = rd_varint(pb, pend, &pat);
                    if (lid < MAX_IDS) {
                        uint64_t name = fn_name_idx[loc_fn_id[lid]];
                        if (str_is(name, "test::keeper")) keeper = true;
                        if (str_is(name, "test::churn"))  churn = true;
                    }
                }
            } else if (sno == 2 && sw == 2) {             // packed values
                size_t pat = poff, pend = poff + plen;
                while (pat < pend && n_vals < 4)
                    vals[n_vals++] = rd_varint(pb, pend, &pat);
            }
        }
        CHECK(n_vals == 2, "two sample values (objects, bytes)");
        total_bytes += vals[1];
        if (keeper) keeper_bytes += vals[1];
        if (churn)  churn_bytes += vals[1];
    }
    CHECK(total_bytes == bytes3, "pb totals equal the live record set");
    CHECK(keeper_bytes >= (size_t)KEEP_BIG * BIG_LEN,
          "keeper site carries the big survivors");
    CHECK(keeper_bytes < bytes0, "keeper site excludes the dropped bigs");
    CHECK(churn_bytes > 0, "churn survivors attributed to their site");

    unlink(MASSIF_PATH);
    unlink(PB_PATH);
    printf("OK\n");
    exit(0);
}
