// String-building workloads: today's runtime primitives vs the fat-string
// prototypes, all on the same yafllib (the worktree's, with array_cap_offset).
//
// Build with -DFAT16 for the 16-byte value (fatstr16.h), else 32-byte.
// usage: bench2 WORKLOAD IMPL [SCALE]
//   WORKLOAD: append1 appendmix readevery small fork tree chars
//             retain retainsparse movetest
//   IMPL:     flat (string_append / concat_n / tagged chars)
//             builder (deforested loop)  builderobj (StringBuilder object)
//             fat  fatinto (tree only: updated in place, not by value)
// Every loop back edge has a GC_SAFE_POINT, as codegen emits. Every run
// prints a content hash so impls can be checked against each other.
#include "yafl.h"
#ifdef FAT16
#include "fatstr16.h"
#else
#include "fatstr32.h"
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>
#include <unistd.h>

#define RING 4096

static object_t* acc;                 // flat/builder accumulator
static object_t* sbobj;               // simulated StringBuilder object
static object_t* base;                // fork workload's shared prefix
static fstr_t    facc, fbase;         // fat accumulators
static object_t* ring[RING];          // retained results (flat)
static fstr_t    fring[RING];         // retained results (fat)
static object_t* piece[4];            // pieces as runtime strings (roots)
static long       nretained;          // retain workload: population size
static object_t** rflat;              // retained flat strings (roots)
static fstr_t*    rfat;               // retained fat strings (roots)

static roots_declaration_func_t prev_roots;
static void declare_roots(void(*declare)(object_t**)) {
    prev_roots(declare);
    declare(&acc); declare(&sbobj); declare(&base);
    declare(&facc.head); declare(&fbase.head);
    for (int i = 0; i < RING; i++) { declare(&ring[i]); declare(&fring[i].head); }
    for (int i = 0; i < 4; i++) declare(&piece[i]);
    for (long i = 0; i < nretained; i++) {
        if (rflat) declare(&rflat[i]);
        if (rfat)  declare(&rfat[i].head);
    }
}
static void set_root(object_t** slot, object_t* v) {
    gc_root_overwrite(slot); *slot = v; gc_root_publish(v);
}
static void set_froot(fstr_t* slot, fstr_t v) {
    gc_root_overwrite(&slot->head); *slot = v;
    if (fstr_heap(v)) gc_root_publish(fstr_heap(v));
}

struct sb { object_t parent; object_t* buf; object_t* off; };
static vtable_t sb_vt = {
    .object_size = sizeof(struct sb),
    .object_pointer_locations = maskof(struct sb, .buf) | maskof(struct sb, .off),
    .name = "sb", .implements_array = VTABLE_IMPLEMENTS(0),
};

static const char* PIECE_TEXT[4] = { "x", "hello", "hello world!", "the quick brown fox jumps over" };
static uint32_t plen[4];

static double cpu_now(void) {
    struct timespec t; clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}

static uint32_t flat_hash(object_t* s) {
    intptr_t b; int32_t n; char* c = string_to_cstr(s, &b, &n);
    return fnv_bytes(2166136261u, (const uint8_t*)c, (uint32_t)n);
}

static fstr_t fstr_of(const char* text) {
    return fstr_append_bytes(fstr_empty(), (const uint8_t*)text, (uint32_t)strlen(text));
}

static const char* workload; static const char* impl; static long scale;

static void churn(long objects) {
    for (long i = 0; i < objects; i++) {
        struct sb* g = object_new(&sb_vt);
        g->buf = NULL; g->off = NULL;
        GC_SAFE_POINT();
    }
}

// ── linear accumulation ────────────────────────────────────────────────────
// `mix`: pieces cycle through 1/5/12/30 bytes; else all 1 byte.
// `readevery`: peek the last byte every 64 appends (a reader mid-build).
static void linear(long total, int mix, int readevery, uint32_t* hash, long* count) {
    long made = 0, n = 0; uint32_t peek = 0;
    if (!strcmp(impl, "fat")) {
        set_froot(&facc, fstr_empty());
        while (made < total) {
            int k = mix ? n % 4 : 0;
            set_froot(&facc, fstr_append_bytes(facc, (const uint8_t*)PIECE_TEXT[k], plen[k]));
            made += plen[k]; n++;
            if (readevery && n % 64 == 0) peek += fstr_byte_at(facc, (uint32_t)made - 1);
            GC_SAFE_POINT();
        }
        *hash = fstr_hash(facc) ^ peek;
    } else if (!strcmp(impl, "flat")) {
        set_root(&acc, STR(""));
        while (made < total) {
            int k = mix ? n % 4 : 0;
            set_root(&acc, string_append(acc, piece[k]));
            made += plen[k]; n++;
            if (readevery && n % 64 == 0) peek += string_byte_at(acc, integer_from_int32((int32_t)made - 1));
            GC_SAFE_POINT();
        }
        *hash = flat_hash(acc) ^ peek;
    } else {   // builder / builderobj: the deforested loop, optionally + object
        int obj = !strcmp(impl, "builderobj");
        set_root(&acc, STR(""));
        while (made < total) {
            int k = mix ? n % 4 : 0;
            object_t* b = string_builder_reserve(acc, integer_from_int32((int32_t)made), integer_from_int32(plen[k]));
            string_copy_to_dangerously(b, integer_from_int32((int32_t)made), piece[k]);
            set_root(&acc, b);
            made += plen[k]; n++;
            if (obj) {
                struct sb* s = object_new(&sb_vt);
                s->buf = b; s->off = integer_from_int32((int32_t)made);
                set_root(&sbobj, (object_t*)s);
            }
            // A mid-build reader of a builder must snapshot (string_resize).
            if (readevery && n % 64 == 0)
                peek += string_byte_at(string_resize(acc, integer_from_int32((int32_t)made)),
                                       integer_from_int32((int32_t)made - 1));
            GC_SAFE_POINT();
        }
        *hash = flat_hash(string_resize(acc, integer_from_int32((int32_t)made))) ^ peek;
    }
    *count = n;
}

// ── many small strings ─────────────────────────────────────────────────────
// `name_<nnn>_value[_longer]`: 15 or 21 bytes from 4 pieces, retained in a
// ring. flat = one exact concat_n, as `a+b+c+d` emits.
static void small(long count, uint32_t* hash) {
    uint32_t h = 0;
    static const char* digits = "0123456789";
    for (long i = 0; i < count; i++) {
        char num[3] = { digits[i / 100 % 10], digits[i / 10 % 10], digits[i % 10] };
        if (!strcmp(impl, "fat")) {
            fstr_t s = fstr_empty();
            s = fstr_append_bytes(s, (const uint8_t*)"name_", 5);
            s = fstr_append_bytes(s, (const uint8_t*)num, 3);
            s = fstr_append_bytes(s, (const uint8_t*)"_", 1);
            s = fstr_append_bytes(s, (const uint8_t*)(i & 1 ? "value" : "value_longer"), i & 1 ? 5 : 12);
            set_froot(&fring[i % RING], s);
            h += fstr_hash(s);
        } else {
            object_t* n = string_from_bytes((uint8_t*)num, 3);
            object_t* s = string_concat_n(4, STR("name_"), n, STR("_"),
                                          i & 1 ? STR("value") : STR("value_longer"));
            set_root(&ring[i % RING], s);
            h += flat_hash(s);
        }
        GC_SAFE_POINT();
    }
    *hash = h;
}

// ── forks from one shared prefix ───────────────────────────────────────────
static void fork_(long count, uint32_t* hash) {
    uint32_t h = 0;
    if (!strcmp(impl, "fat")) {
        fstr_t b = fstr_empty();
        for (int i = 0; i < 1024; i++) { b = fstr_append_bytes(b, (const uint8_t*)"y", 1); GC_SAFE_POINT(); }
        set_froot(&fbase, b);
        for (long i = 0; i < count; i++) {
            int k = i % 4;
            fstr_t s = fstr_append_bytes(fbase, (const uint8_t*)PIECE_TEXT[k], plen[k]);
            set_froot(&fring[i % RING], s);
            h += fstr_hash(s);
            GC_SAFE_POINT();
        }
    } else {
        char tmp[1024]; memset(tmp, 'y', sizeof tmp);
        set_root(&base, string_from_bytes((uint8_t*)tmp, 1024));
        for (long i = 0; i < count; i++) {
            object_t* s = string_append(base, piece[i % 4]);
            set_root(&ring[i % RING], s);
            h += flat_hash(s);
            GC_SAFE_POINT();
        }
    }
    *hash = h;
}

// ── balanced tree of concatenations (pretty-printer shape) ─────────────────
static object_t* tree_flat(long lo, long hi) {
    if (hi - lo == 1) return piece[lo % 4];
    long mid = (lo + hi) / 2;
    object_t* l = tree_flat(lo, mid);   // held on the C stack: conservatively scanned
    object_t* r = tree_flat(mid, hi);
    GC_SAFE_POINT();
    return string_append(l, r);
}
static fstr_t tree_fat(long lo, long hi) {
    if (hi - lo == 1) {
        int k = lo % 4;
        return fstr_append_bytes(fstr_empty(), (const uint8_t*)PIECE_TEXT[k], plen[k]);
    }
    long mid = (lo + hi) / 2;
    fstr_t l = tree_fat(lo, mid);
    fstr_t r = tree_fat(mid, hi);
    GC_SAFE_POINT();
    return fstr_append(l, r);
}
static void tree_fat_into(long lo, long hi, fstr_t* out) {
    if (hi - lo == 1) {
        int k = lo % 4;
        *out = fstr_empty();
        fstr_append_bytes_into(out, (const uint8_t*)PIECE_TEXT[k], plen[k]);
        return;
    }
    long mid = (lo + hi) / 2;
    fstr_t r;
    tree_fat_into(lo, mid, out);
    tree_fat_into(mid, hi, &r);
    GC_SAFE_POINT();
    fstr_append_into(out, &r);
}

// ── single characters ──────────────────────────────────────────────────────
// Scan text; each byte becomes a 1-character string, passed through a
// non-inlined classifier that compares it against literals and returns a
// short word. Today: tagged pointers + string_eq. Fat: inline values.
static uint8_t* text;
static object_t *L_NL, *L_SP, *L_A, *W_LINE, *W_SPACE, *W_UPPER, *W_OTHER;
static fstr_t F_NL, F_SP, F_A, FW_LINE, FW_SPACE, FW_UPPER, FW_OTHER;

static __attribute__((noinline)) object_t* classify_flat(object_t* c) {
    if (string_eq(c, L_NL)) return W_LINE;
    if (string_eq(c, L_SP)) return W_SPACE;
    if (string_eq(c, L_A))  return W_UPPER;
    return W_OTHER;
}
static __attribute__((noinline)) fstr_t classify_fat(fstr_t c) {
    if (fstr_eq(c, F_NL)) return FW_LINE;
    if (fstr_eq(c, F_SP)) return FW_SPACE;
    if (fstr_eq(c, F_A))  return FW_UPPER;
    return FW_OTHER;
}
static void chars(long n, uint32_t* hash) {
    static const char alphabet[] = "abcdefghijklmnopqrstuvwxyz  \nAAB";
    text = malloc(n);
    uint64_t r = 88172645463325252ull;
    for (long i = 0; i < n; i++) { r ^= r << 13; r ^= r >> 7; r ^= r << 17; text[i] = alphabet[r % 32]; }
    L_NL = STR("\n"); L_SP = STR(" "); L_A = STR("A");
    W_LINE = STR("line"); W_SPACE = STR("space"); W_UPPER = STR("upper"); W_OTHER = STR("other");
    F_NL = fstr_of("\n"); F_SP = fstr_of(" "); F_A = fstr_of("A");
    FW_LINE = fstr_of("line"); FW_SPACE = fstr_of("space"); FW_UPPER = fstr_of("upper"); FW_OTHER = fstr_of("other");
    uint32_t h = 0;
    if (!strcmp(impl, "fat")) {
        for (long i = 0; i < n; i++) {
            fstr_t c = fstr_append_bytes(fstr_empty(), &text[i], 1);
            fstr_t w = classify_fat(c);
            h = h * 31 + fstr_length(w) + (uint32_t)fstr_byte_at(w, 0);
            GC_SAFE_POINT();
        }
    } else {
        for (long i = 0; i < n; i++) {
            object_t* c = ascii_to_string(text[i]);
            object_t* w = classify_flat(c);
            h = h * 31 + (uint32_t)string_length(w) + (uint32_t)string_byte_at(w, integer_from_int32(0));
            GC_SAFE_POINT();
        }
    }
    *hash = h;
}

// ── retained population: slack over time ───────────────────────────────────
// N strings of 20..5000 bytes (log-uniform), each built from mixed small
// appends and kept for the rest of the run. `sparse` interleaves garbage so
// the strings' pages go sparse and get compacted; dense packs them. Then
// garbage churn drives several GC cycles. Footprint = heap pages in use.
extern size_t memory_count(void);
static uint64_t rng = 88172645463325252ull;
static uint32_t rnd(void) { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return (uint32_t)rng; }

static void report(const char* phase, long live_bytes) {
    long long pages = (long long)memory_count();
    long long reserved = 0, used = 0;
    if (rfat) for (long i = 0; i < nretained; i++) if (fstr_heap(rfat[i])) {
        reserved += buf_cap(fstr_heap(rfat[i])); used += buf_used(fstr_heap(rfat[i])); }
    printf("  %-9s heap=%7.1fMB (%.2fx live)", phase, pages * (double)GC_PAGE_SIZE / 1e6,
           pages * (double)GC_PAGE_SIZE / live_bytes);
    if (rfat) printf("  claimed-cap/used=%.2f", (double)reserved / (used ? used : 1));
    printf("\n");
}

static void retain(long n, int sparse, uint32_t* hash) {
    nretained = n;
    if (!strcmp(impl, "fat")) rfat = calloc(n, sizeof *rfat); else rflat = calloc(n, sizeof *rflat);
    if (rfat) for (long i = 0; i < n; i++) rfat[i] = fstr_empty();
    long live = 0; uint32_t h = 0;
    for (long i = 0; i < n; i++) {
        double u = (rnd() & 0xffffff) / (double)0x1000000;
        long target = (long)(20.0 * pow(250.0, u));        // log-uniform [20, 5000]
        long made = 0, k = 0;
        if (rfat) {
            set_froot(&facc, fstr_empty());
            while (made < target) {
                int q = k++ % 4;
                set_froot(&facc, fstr_append_bytes(facc, (const uint8_t*)PIECE_TEXT[q], plen[q]));
                made += plen[q];
                GC_SAFE_POINT();
            }
            set_froot(&rfat[i], facc);
            h += fstr_hash(facc);
        } else {   // today's StringBuilder: deforested loop, exact-size toString
            set_root(&acc, STR(""));
            while (made < target) {
                int q = k++ % 4;
                object_t* b = string_builder_reserve(acc, integer_from_int32((int32_t)made), integer_from_int32(plen[q]));
                string_copy_to_dangerously(b, integer_from_int32((int32_t)made), piece[q]);
                set_root(&acc, b);
                made += plen[q];
                GC_SAFE_POINT();
            }
            set_root(&rflat[i], string_resize(acc, integer_from_int32((int32_t)made)));
            h += flat_hash(rflat[i]);
        }
        live += made;
        if (sparse) churn(made / 8);        // ~4x the string's size in 32-byte garbage
    }
    *hash = h;
    report("built", live);
    for (int phase = 1; phase <= 4; phase++) {
        churn(4000000);                     // 128 MB of garbage: several cycles
        char name[16]; snprintf(name, sizeof name, "churn%d", phase);
        report(name, live);
    }
    uint32_t check = 0;
    for (long i = 0; i < n; i++) check += rfat ? fstr_hash(rfat[i]) : flat_hash(rflat[i]);
    if (check != h) { printf("CONTENT CHANGED\n"); exit(3); }
}

// ── relocation safety: extend a buffer AFTER compaction has moved it ───────
// Deterministic, after tests/test_gc_fwd_chain.c: manual GC mode, the buffer
// built and buried in its own frame, stack + callee-saved registers scrubbed,
// then exactly one cycle. Oracle: an in-place append on a MOVED buffer whose
// new length exceeds what the compactor copied has written past the object.
// Run with YAFL_THREADS=1.
extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
static volatile uintptr_t g_before;       // plain global: not a root, not scanned

static void run_one_cycle(void) {
    long guard = 0;
    do { gc_debug_step(); if (++guard > 10000000) { printf("no cycle\n"); exit(4); } }
    while (gc_debug_stage() == 1);
    while (gc_debug_stage() != 1) { gc_debug_step(); if (++guard > 10000000) { printf("stuck\n"); exit(4); } }
}
static __attribute__((noinline)) void build_and_bury(void) {
    set_froot(&facc, fstr_empty());
    for (int i = 0; i < 40; i++)             // ~480 B: head with slack
        set_froot(&facc, fstr_append_bytes(facc, (const uint8_t*)"hello world!", 12));
    g_before = (uintptr_t)fstr_heap(facc);
    for (int i = 0; i < 1000; i++) { volatile object_t* f = object_new(&sb_vt); (void)f; }
}
static __attribute__((noinline)) void scrub(void) {
    volatile uintptr_t junk[512];
    for (int i = 0; i < 512; ++i) junk[i] = (uintptr_t)(i * 2 + 1);
    __asm__ volatile("" :: "r"(junk[0]), "r"(junk[511]) : "memory", "rbx", "r12", "r13", "r14", "r15");
}
static __attribute__((noinline)) bool was_moved(void) {
    return vtable_is_forward(((object_t*)g_before)->vtable);
}
static long moved, inplace_after_move, overflow, notmoved;
static __attribute__((noinline)) void extend_after_move(uint32_t* h) {
    object_t* hd = object_resolve(fstr_heap(facc));
    fstr_t cur = facc; cur.head = hd;
    set_froot(&facc, cur);
    size_t copied = (object_get_size(hd) + GC_ALLOC_GRANULE - 1) / GC_ALLOC_GRANULE * GC_ALLOC_GRANULE;
    fstr_t out = fstr_append_bytes(facc, (const uint8_t*)"the quick brown fox jumps over", 30);
    if (fstr_heap(out) == hd) {
        inplace_after_move++;
        if (offsetof(string_t, array) + (size_t)fstr_head_len(out) + 1 > copied) overflow++;
    }
    set_froot(&facc, out);
    *h += fstr_hash(facc);
}
static void movetest(long rounds, uint32_t* hash) {
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);
    uint32_t h = 0;
    for (long r = 0; r < rounds; r++) {
        build_and_bury();
        scrub();
        run_one_cycle();
        if (!was_moved()) { notmoved++; continue; }
        moved++;
        extend_after_move(&h);
    }
    printf("  rounds=%ld moved=%ld not-moved=%ld inplace-after-move=%ld OVERFLOWS=%ld\n",
           rounds, moved, notmoved, inplace_after_move, overflow);
    *hash = h;
}

static void run(object_t* unused, fun_t k) {
    (void)unused;
    for (int i = 0; i < 4; i++) {
        plen[i] = (uint32_t)strlen(PIECE_TEXT[i]);
        piece[i] = string_from_bytes((uint8_t*)PIECE_TEXT[i], (int32_t)plen[i]);
    }
    set_froot(&facc, fstr_empty()); set_froot(&fbase, fstr_empty());
    for (int i = 0; i < RING; i++) fring[i] = fstr_empty();

    uint32_t h = 0; long n = scale;
    double t0 = cpu_now();
    if      (!strcmp(workload, "append1"))      linear(scale, 0, 0, &h, &n);
    else if (!strcmp(workload, "appendmix"))    linear(scale, 1, 0, &h, &n);
    else if (!strcmp(workload, "readevery"))    linear(scale, 1, 1, &h, &n);
    else if (!strcmp(workload, "small"))        small(scale, &h);
    else if (!strcmp(workload, "fork"))         fork_(scale, &h);
    else if (!strcmp(workload, "chars"))        chars(scale, &h);
    else if (!strcmp(workload, "retain"))       retain(scale, 0, &h);
    else if (!strcmp(workload, "retainsparse")) retain(scale, 1, &h);
    else if (!strcmp(workload, "movetest"))     movetest(scale, &h);
    else if (!strcmp(workload, "tree")) {
        if (!strcmp(impl, "fat"))          { fstr_t r = tree_fat(0, scale); set_froot(&facc, r); h = fstr_hash(facc); }
        else if (!strcmp(impl, "fatinto")) { fstr_t r; tree_fat_into(0, scale, &r); set_froot(&facc, r); h = fstr_hash(facc); }
        else { set_root(&acc, tree_flat(0, scale)); h = flat_hash(acc); }
    }
    else { printf("unknown workload %s\n", workload); exit(2); }
    double t1 = cpu_now();
    printf("%-12s %-10s scale=%-9ld cpu=%7.3fs ns/op=%8.1f hash=%08x\n",
           workload, strcmp(impl, "fat") && strcmp(impl, "fatinto") ? impl : FAT_NAME,
           scale, t1 - t0, (t1 - t0) * 1e9 / n, h);
#ifdef FAT_STATS
    printf("  inplace=%ld (%lld B) copy=%ld (%lld B)\n", fs_inplace, fs_bytes_inplace, fs_copy, fs_bytes_copy);
#endif
    fflush(stdout);
    ((void(*)(object_t*, object_t*))k.f)(k.o, integer_from_int32(0));
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: bench2 WORKLOAD IMPL [SCALE]\n"); return 2; }
    workload = argv[1]; impl = argv[2]; scale = argc > 3 ? atol(argv[3]) : 1000000;
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run);
}
