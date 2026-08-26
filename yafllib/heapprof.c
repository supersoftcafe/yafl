// Heap-pressure profiling, layer 1 (docs/heap-profiling-design.md).
//
// Census at the collection boundary: every object the marker first-marks or
// the scavenger copies bumps a per-thread {vtable -> bytes} table; the
// exclusive prune tail merges the tables into one massif snapshot per GC
// cycle. Massif is emitted directly (the callgrind-without-valgrind trick):
// snapshots carry a one-level tree — (heap) over per-type live bytes — so
// ms_print and massif-visualizer read the file as-is.
#define _GNU_SOURCE
#include "heapprof.h"

#include <inttypes.h>
#include <math.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <threads.h>
#include <time.h>
#include <unistd.h>

#include "yafl.h"
#include "prof.h"

bool yafl_heapprof_enabled = false;
bool yafl_heapprof_sample_enabled = false;

// Per-thread open-addressing table, vtable-pointer keyed. 1024 slots holds
// every distinct type in any program we have seen with headroom; overflow
// falls into a shared "(other)" bucket rather than dropping bytes.
#define HP_SLOTS 1024

typedef struct {
    const struct vtable *key[HP_SLOTS];
    uint64_t bytes[HP_SLOTS];
    uint64_t other;                     // overflow bytes, never dropped
} hp_table_t;

// Registry of every thread's table (CAS-push list, the prof.c pattern).
typedef struct hp_node {
    hp_table_t table;
    struct hp_node *next;
} hp_node_t;

static _Atomic(hp_node_t *) hp_threads = NULL;
static thread_local hp_table_t *hp_tl = NULL;

static FILE *hp_out = NULL;
static uint64_t hp_snapshot = 0;
static uint64_t hp_t0_ms = 0;

static uint64_t hp_now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000u + (uint64_t)(ts.tv_nsec / 1000000);
}

static void hp2_init(const char *massif_path);

void yafl_heapprof_init(void) {
    const char *path = getenv("YAFL_HEAPPROF");
    if (path == NULL)
        return;
    char buf[256];
    if (path[0] == '\0') {
        snprintf(buf, sizeof buf, "massif.out.%ld", (long)getpid());
        path = buf;
    }
    hp_out = fopen(path, "w");
    if (hp_out == NULL) {
        fprintf(stderr, "[HEAPPROF] cannot open %s\n", path);
        return;
    }
    fprintf(hp_out,
            "desc: yafl live census (bytes visited per GC cycle by type)\n"
            "cmd: (yafl)\n"
            "time_unit: ms\n");
    hp_t0_ms = hp_now_ms();
    yafl_heapprof_enabled = true;
    atexit(yafl_heapprof_dump);
    fprintf(stderr, "[HEAPPROF] writing %s\n", path);
    hp2_init(path);
}

void yafl_heapprof_thread_init(void) {
    if (!yafl_heapprof_enabled || hp_tl != NULL)
        return;
    hp_node_t *node = calloc(1, sizeof *node);
    if (node == NULL)
        return;
    hp_node_t *head = atomic_load(&hp_threads);
    do {
        node->next = head;
    } while (!atomic_compare_exchange_weak(&hp_threads, &head, node));
    hp_tl = &node->table;
}

void yafl_heapprof_census(const struct vtable *vt, size_t bytes) {
    hp_table_t *t = hp_tl;
    if (t == NULL) {
        // Threads can reach a mark before their declaration hook ran
        // (ordering differs between the main thread and workers): lazily
        // self-register — the registry push is lock-free.
        yafl_heapprof_thread_init();
        t = hp_tl;
        if (t == NULL)
            return;
    }
    // Pointer-hash probe; vtables are stable addresses for the process
    // lifetime, so the key never moves under us.
    uintptr_t h = ((uintptr_t)vt) >> 4;
    for (unsigned probe = 0; probe < 32; probe++) {
        unsigned idx = (unsigned)((h + probe) & (HP_SLOTS - 1));
        if (t->key[idx] == vt) {
            t->bytes[idx] += bytes;
            return;
        }
        if (t->key[idx] == NULL) {
            t->key[idx] = vt;
            t->bytes[idx] = bytes;
            return;
        }
    }
    t->other += bytes;
}

// Merge scratch, cycle-local (single-threaded caller).
typedef struct {
    const struct vtable *vt;
    uint64_t bytes;
} hp_row_t;

static int hp_row_cmp(const void *a, const void *b) {
    const hp_row_t *ra = a, *rb = b;
    if (ra->bytes != rb->bytes)
        return ra->bytes < rb->bytes ? 1 : -1;   // descending
    return strcmp(((const vtable_t *)ra->vt)->name,
                  ((const vtable_t *)rb->vt)->name);
}

void yafl_heapprof_cycle_end(size_t in_use_bytes, size_t reserved_bytes) {
    if (!yafl_heapprof_enabled || hp_out == NULL)
        return;
    static hp_row_t rows[HP_SLOTS];
    unsigned n = 0;
    uint64_t other = 0, census_total = 0;
    for (hp_node_t *node = atomic_load(&hp_threads); node; node = node->next) {
        hp_table_t *t = &node->table;
        for (unsigned i = 0; i < HP_SLOTS; i++) {
            if (t->key[i] == NULL)
                continue;
            unsigned j = 0;
            for (; j < n; j++)
                if (rows[j].vt == t->key[i])
                    break;
            if (j == n && n < HP_SLOTS)
                rows[n++] = (hp_row_t){t->key[i], 0};
            if (j < n)
                rows[j].bytes += t->bytes[i];
            census_total += t->bytes[i];
            t->key[i] = NULL;
            t->bytes[i] = 0;
        }
        other += t->other;
        census_total += t->other;
        t->other = 0;
    }
    qsort(rows, n, sizeof rows[0], hp_row_cmp);

    uint64_t extra = reserved_bytes > in_use_bytes ? reserved_bytes - in_use_bytes : 0;
    fprintf(hp_out,
            "#-----------\nsnapshot=%" PRIu64 "\n#-----------\n"
            "time=%" PRIu64 "\n"
            "mem_heap_B=%zu\n"
            "mem_heap_extra_B=%" PRIu64 "\n"
            "mem_stacks_B=0\n"
            "heap_tree=detailed\n",
            hp_snapshot++, hp_now_ms() - hp_t0_ms, in_use_bytes, extra);
    // One-level tree: the census total over per-type children. massif wants
    // the parent's byte count to cover its children; the (visited) root is
    // the cycle's census, shown under the heap total.
    fprintf(hp_out, "n%u: %" PRIu64 " (visited this cycle, by type)\n",
            n + (other ? 1 : 0), census_total);
    for (unsigned j = 0; j < n; j++)
        fprintf(hp_out, " n0: %" PRIu64 " 0x0: %s\n",
                rows[j].bytes, ((const vtable_t *)rows[j].vt)->name);
    if (other)
        fprintf(hp_out, " n0: %" PRIu64 " 0x0: (other)\n", other);
    fflush(hp_out);
}

// ═══ layer 2: allocation-site inuse_space → pprof ══════════════════════════
//
// See heapprof.h for the model. Concurrency here is deliberately simple:
// one spinlock covers record INSERTS (mutators, once per sampled
// acquisition), the SWEEP (single-threaded exclusive prune tail, but
// concurrent with running mutators) and the DUMP. The forward hook probes
// lock-free: it runs in the prune BODY, phase-disjoint from the tail's
// sweep, and only ever plain-stores into an already-published record.

// Sizes proven on the heap-profiled self-compile: live samples at the
// default 64 KiB rate on a ~1 GB live heap are ~16k (records), while
// UNIQUE allocation stacks accumulate for the whole run — a self-compile
// exceeded 128k distinct depth-64 windows, so the table is sized in the
// hundreds of thousands and the window kept shallow. Tables are calloc'd:
// virtual until touched, so the cost is proportional to real diversity.
enum {
    HP2_RECORDS     = 1 << 16,     // sampled live objects (open addressing)
    HP2_REC_PROBE   = 64,
    HP2_STACKS      = 1 << 19,     // unique allocation stacks
    HP2_STACK_PROBE = 64,
    HP2_POOL_CAP    = 1 << 25,     // u32 ids backing the stacks
};

#define HP2_TOMBSTONE ((uintptr_t)1)   // deleted slot: probes continue past

typedef struct {
    _Atomic(uintptr_t) addr;       // 0 empty / 1 tombstone; published LAST
    void*    fwd;                  // forward target seen this cycle
    uint32_t stack;                // slot in hp2_stacks, or UINT32_MAX
    uint32_t bytes;                // sampled object size
} hp2_rec_t;

typedef struct {
    uint64_t hash;                 // 0 = empty
    uint32_t off, len;             // frames in hp2_pool, root first
} hp2_stack_t;

static hp2_rec_t*      hp2_recs = NULL;
static hp2_stack_t*    hp2_stacks = NULL;
static uint32_t*       hp2_pool = NULL;
static uint32_t        hp2_pool_used = 0;
static uint64_t        hp2_rate = 0;
static _Atomic(int64_t) hp2_debt = 0;
static _Atomic(bool)   hp2_lock_word = false;
static uint64_t        hp2_dropped = 0;       // records lost to table limits
static uint64_t        hp2_stack_fail_pool = 0;   // insert failures by cause
static uint64_t        hp2_stack_fail_probe = 0;
static char            hp2_path[512];

static void hp2_lock(void) {
    while (atomic_exchange_explicit(&hp2_lock_word, true, memory_order_acquire))
        ;
}

static void hp2_unlock(void) {
    atomic_store_explicit(&hp2_lock_word, false, memory_order_release);
}

static void hp2_init(const char *massif_path) {
    const char *sample = getenv("YAFL_HEAPPROF_SAMPLE");
    if (sample == NULL || sample[0] == '\0')
        return;
    uint64_t rate = strtoull(sample, NULL, 10);
    if (rate == 0)
        return;
    if (!yafl_prof_enabled) {
        fprintf(stderr, "[HEAPPROF] YAFL_HEAPPROF_SAMPLE needs a --profile "
                        "binary (no shadow stack to attribute sites)\n");
        return;
    }
    hp2_recs = calloc(HP2_RECORDS, sizeof *hp2_recs);
    hp2_stacks = calloc(HP2_STACKS, sizeof *hp2_stacks);
    hp2_pool = calloc(HP2_POOL_CAP, sizeof *hp2_pool);
    if (hp2_recs == NULL || hp2_stacks == NULL || hp2_pool == NULL) {
        free(hp2_recs); free(hp2_stacks); free(hp2_pool);
        hp2_recs = NULL; hp2_stacks = NULL; hp2_pool = NULL;
        return;
    }
    snprintf(hp2_path, sizeof hp2_path, "%s.heap.pb.gz", massif_path);
    hp2_rate = rate;
    atomic_store(&hp2_debt, (int64_t)rate);
    yafl_heapprof_sample_enabled = true;
    fprintf(stderr, "[HEAPPROF] sampling sites every %" PRIu64 " bytes -> %s\n",
            rate, hp2_path);
}

// Hash-cons a composed frame window into the stack table (caller holds
// the lock). Frames are root-first. Returns the slot, or UINT32_MAX on
// overflow.
//
// Slot placement scatters the MIXED hash and probes by an odd double-hash
// step. Both matter: raw FNV low bits over short sequences of small
// integer ids cluster, and linear probing turned those clusters into
// permanent occupied walls — stacks are never deleted — that made a few
// unlucky-hot stacks fail EVERY insert (789k probe failures on a
// 1.5%-occupied table in the first counter-instrumented self-compile).
static uint32_t hp2_stack_insert(const uint32_t* ids, uint32_t len) {
    uint64_t h = 0xcbf29ce484222325ull;
    for (uint32_t i = 0; i < len; i++) {
        h ^= ids[i];
        h *= 0x100000001b3ull;
    }
    if (h == 0)
        h = 1;
    uint32_t mask = HP2_STACKS - 1;
    uint32_t mix = (uint32_t)(h >> 32) ^ (uint32_t)h;
    uint32_t slot = (mix * 0x9e3779b1u) & mask;
    uint32_t step = ((mix >> 15) | 1u);
    for (int probe = 0; probe < HP2_STACK_PROBE; probe++, slot = (slot + step) & mask) {
        hp2_stack_t* s = &hp2_stacks[slot];
        if (s->hash == 0) {
            if ((uint64_t)hp2_pool_used + len > HP2_POOL_CAP) {
                hp2_stack_fail_pool++;
                return UINT32_MAX;
            }
            for (uint32_t i = 0; i < len; i++)
                hp2_pool[hp2_pool_used + i] = ids[i];
            s->off = hp2_pool_used;
            s->len = len;
            s->hash = h;
            hp2_pool_used += len;
            return slot;
        }
        if (s->hash == h && s->len == len) {
            bool same = true;
            for (uint32_t i = 0; i < len && same; i++)
                same = hp2_pool[s->off + i] == ids[i];
            if (same)
                return slot;
        }
    }
    hp2_stack_fail_probe++;
    return UINT32_MAX;
}

static uint32_t hp2_rec_slot(uintptr_t addr) {
    return (uint32_t)((addr >> 4) * 0x9e3779b97f4a7c15ull >> 40) & (HP2_RECORDS - 1);
}

void yafl_heapprof_sample_alloc(void *addr, size_t object_bytes,
                                size_t acquired_bytes) {
    if (!yafl_heapprof_sample_enabled)
        return;
    int64_t after = atomic_fetch_sub_explicit(&hp2_debt, (int64_t)acquired_bytes,
                                              memory_order_relaxed)
                    - (int64_t)acquired_bytes;
    if (after > 0)
        return;
    // Reset races with concurrent samplers only around the crossing point;
    // an occasional double sample or double reset shifts one sample, never
    // corrupts state.
    atomic_store_explicit(&hp2_debt, (int64_t)hp2_rate, memory_order_relaxed);

    // This thread's own shadow stack (allocation runs on the sampled
    // thread), CAPPED to the deepest HP2_MAX_DEPTH frames with a
    // (truncated) pseudo-frame standing for the elided ancestry. The cap
    // is what makes hash-consing viable at compiler scale: recursion makes
    // every DEPTH of a walk a distinct full stack (the first self-compile
    // run lost 13k records' stacks to pool exhaustion), while leaf-side
    // windows of a recursive chain converge to a handful of unique stacks
    // — the same reason Go caps its heap-profile stacks. Frames past the
    // shadow-stack cap were never stored (counted only): that loses the
    // LEAF side instead, marked with a (truncated) leaf like the CPU
    // sampler's samples.
    enum { HP2_MAX_DEPTH = 32 };
    yafl_prof_tl_t* tl = &yafl_prof_tl;
    uint32_t stored = 0;
    bool leaf_lost = false;
    if (tl->stack != NULL) {
        int32_t sp = atomic_load_explicit(&tl->sp, memory_order_relaxed);
        stored = sp > tl->cap ? (uint32_t)tl->cap : (sp > 0 ? (uint32_t)sp : 0);
        leaf_lost = sp > tl->cap;
    }

    // Insert with a RETRY LADDER: on a probe-bound failure, shrink the
    // window and try again. Shorter leaf-side windows converge onto
    // already-resident stacks (a depth-1 window is just the leaf frame),
    // so attribution degrades gracefully — ancestry shortens, the datum
    // survives.
    static const uint32_t rungs[] = { HP2_MAX_DEPTH, 16, 4, 1 };
    hp2_lock();
    uint32_t stack = UINT32_MAX;
    for (unsigned r = 0; r < sizeof rungs / sizeof rungs[0]; r++) {
        uint32_t take = stored < rungs[r] ? stored : rungs[r];
        uint32_t buf[HP2_MAX_DEPTH + 2];
        uint32_t len = 0;
        if (take < stored)
            buf[len++] = yafl_prof_reserved_id(YAFL_PROF_RES_TRUNCATED);
        for (uint32_t i = 0; i < take; i++)
            buf[len++] = tl->stack[stored - take + i];
        if (leaf_lost)
            buf[len++] = yafl_prof_reserved_id(YAFL_PROF_RES_TRUNCATED);
        if (len == 0)
            buf[len++] = yafl_prof_reserved_id(YAFL_PROF_RES_RUNTIME);
        stack = hp2_stack_insert(buf, len);
        if (stack != UINT32_MAX || take == stored)
            break;                 // shrinking further would change nothing
    }
    uint32_t slot = hp2_rec_slot((uintptr_t)addr);
    bool placed = false;
    for (int probe = 0; probe < HP2_REC_PROBE && !placed;
         probe++, slot = (slot + 1) & (HP2_RECORDS - 1)) {
        hp2_rec_t* r = &hp2_recs[slot];
        uintptr_t key = atomic_load_explicit(&r->addr, memory_order_relaxed);
        if (key == 0 || key == HP2_TOMBSTONE) {
            r->fwd = NULL;
            r->stack = stack;
            r->bytes = object_bytes > UINT32_MAX ? UINT32_MAX : (uint32_t)object_bytes;
            // Publish the key last: the forward hook probes without the lock
            // and must only ever see fully-written records.
            atomic_store_explicit(&r->addr, (uintptr_t)addr, memory_order_release);
            placed = true;
        }
    }
    if (!placed)
        hp2_dropped++;
    hp2_unlock();
}

void yafl_heapprof_sample_forwarded(void *old_addr, void *new_addr) {
    if (hp2_recs == NULL)
        return;
    uint32_t slot = hp2_rec_slot((uintptr_t)old_addr);
    for (int probe = 0; probe < HP2_REC_PROBE;
         probe++, slot = (slot + 1) & (HP2_RECORDS - 1)) {
        hp2_rec_t* r = &hp2_recs[slot];
        uintptr_t key = atomic_load_explicit(&r->addr, memory_order_acquire);
        if (key == 0)
            return;                       // never inserted
        if (key == (uintptr_t)old_addr) {
            r->fwd = new_addr;
            return;
        }
    }
}

// Is there a live object STARTING at this address? Valid after prune has
// published the survivor set into the objects bitmap. Freed pages read a
// zeroed tag (madvised, mapping intact); reused pages alias — a record
// whose slot was reused by a fresh object keeps living with the old site,
// the standard (rare, bounded) aliasing every sampling heap profiler has.
static bool hp2_addr_is_live(uintptr_t addr) {
    gc_page_t* page = (gc_page_t*)(addr & ~(uintptr_t)(sizeof(gc_page_t) - 1));
    if (page->head.tag != PAGE_MAGIC_NUMBER)
        return false;
    ptrdiff_t slot = (slot_t*)addr - page->slots;
    if (slot < 0 || slot >= (ptrdiff_t)SLOTS_PER_PAGE)
        return false;
    return (page->head.objects.a[slot / GC_MASK_SIZE]
            >> (slot % GC_MASK_SIZE)) & 1u;
}

void yafl_heapprof_sample_sweep(void) {
    if (hp2_recs == NULL)
        return;
    hp2_lock();
    // Re-key forwarded records first: compaction targets are fresh
    // allocations whose objects bit is already set, so a re-keyed record
    // passes the liveness test below on the same sweep.
    for (uint32_t i = 0; i < HP2_RECORDS; i++) {
        hp2_rec_t* r = &hp2_recs[i];
        uintptr_t key = atomic_load_explicit(&r->addr, memory_order_relaxed);
        if (key <= HP2_TOMBSTONE || r->fwd == NULL)
            continue;
        void*    fwd   = r->fwd;
        uint32_t stack = r->stack;
        uint32_t bytes = r->bytes;
        atomic_store_explicit(&r->addr, HP2_TOMBSTONE, memory_order_relaxed);
        uint32_t slot = hp2_rec_slot((uintptr_t)fwd);
        bool placed = false;
        for (int probe = 0; probe < HP2_REC_PROBE && !placed;
             probe++, slot = (slot + 1) & (HP2_RECORDS - 1)) {
            hp2_rec_t* t = &hp2_recs[slot];
            uintptr_t tkey = atomic_load_explicit(&t->addr, memory_order_relaxed);
            if (tkey == 0 || tkey == HP2_TOMBSTONE) {
                t->fwd = NULL;
                t->stack = stack;
                t->bytes = bytes;
                atomic_store_explicit(&t->addr, (uintptr_t)fwd, memory_order_release);
                placed = true;
            }
        }
        if (!placed)
            hp2_dropped++;
    }
    // Liveness EVERY cycle, not only at majors: the test is exact for pages
    // this cycle pruned (young churn — where nearly all samples die) and
    // conservative for old pages (their objects bitmap keeps dead entries
    // until a major refreshes it: stale records are KEPT, never lost).
    // Sweeping only at majors let dead young records squat in the table
    // between majors and starved inserts — the first self-compile run
    // dropped a million samples that way.
    for (uint32_t i = 0; i < HP2_RECORDS; i++) {
        hp2_rec_t* r = &hp2_recs[i];
        uintptr_t key = atomic_load_explicit(&r->addr, memory_order_relaxed);
        if (key > HP2_TOMBSTONE && !hp2_addr_is_live(key))
            atomic_store_explicit(&r->addr, HP2_TOMBSTONE, memory_order_relaxed);
    }
    hp2_unlock();
}

size_t yafl_heapprof_sample_records(size_t *live_bytes) {
    if (live_bytes)
        *live_bytes = 0;
    if (hp2_recs == NULL)
        return 0;
    hp2_lock();
    size_t n = 0, bytes = 0;
    for (uint32_t i = 0; i < HP2_RECORDS; i++) {
        uintptr_t key = atomic_load_explicit(&hp2_recs[i].addr, memory_order_relaxed);
        if (key > HP2_TOMBSTONE) {
            n++;
            bytes += hp2_recs[i].bytes;
        }
    }
    hp2_unlock();
    if (live_bytes)
        *live_bytes = bytes;
    return n;
}

// ── pprof writer ───────────────────────────────────────────────────────────
// profile.proto, hand-encoded (the callgrind-without-valgrind trick again),
// wrapped in a gzip container of stored deflate blocks so no compression
// library is needed. pprof accepts both; the container keeps the documented
// .pb.gz contract.

typedef struct {
    unsigned char* p;
    size_t n, cap;
    bool overflow;
} hp2_buf_t;

static void hp2_put(hp2_buf_t* b, const void* src, size_t len) {
    if (b->n + len > b->cap) {
        b->overflow = true;
        return;
    }
    memcpy(b->p + b->n, src, len);
    b->n += len;
}

static void hp2_varint(hp2_buf_t* b, uint64_t v) {
    unsigned char tmp[10];
    unsigned n = 0;
    do {
        unsigned char byte = v & 0x7f;
        v >>= 7;
        tmp[n++] = byte | (v ? 0x80 : 0);
    } while (v);
    hp2_put(b, tmp, n);
}

static void hp2_tag(hp2_buf_t* b, unsigned field, unsigned wire) {
    hp2_varint(b, ((uint64_t)field << 3) | wire);
}

static void hp2_submsg(hp2_buf_t* out, unsigned field, const hp2_buf_t* sub) {
    hp2_tag(out, field, 2);
    hp2_varint(out, sub->n);
    hp2_put(out, sub->p, sub->n);
}

// String interning: emitted order = pprof string index. Content-hashed
// open addressing — a compiler-scale profile references thousands of
// distinct function and file names, and a run-out must NEVER silently
// alias to "" (index 0): the first self-compile dump did exactly that
// past a small fixed cap and left 92% of the profile unattributed. On
// the (never-observed) full table the entry is emitted UNINTERNED — a
// duplicate string costs bytes, an empty name costs the datum.
enum { HP2_STR_SLOTS = 1 << 16 };            // open addressing, power of two
typedef struct { const char* s; uint32_t idx; } hp2_str_slot_t;
static hp2_str_slot_t hp2_strtab[HP2_STR_SLOTS];
static unsigned hp2_strn;

static uint64_t hp2_str_emit(hp2_buf_t* out, const char* s) {
    // Emit the string_table entry (field 6) at first use; repeated-field
    // ORDER across the stream defines the index, interleaving is fine.
    hp2_tag(out, 6, 2);
    size_t len = strlen(s);
    hp2_varint(out, len);
    hp2_put(out, s, len);
    return hp2_strn++;
}

static uint64_t hp2_str(hp2_buf_t* out, const char* s) {
    uint64_t h = 0xcbf29ce484222325ull;
    for (const char* p = s; *p; p++) {
        h ^= (unsigned char)*p;
        h *= 0x100000001b3ull;
    }
    uint32_t slot = (uint32_t)h & (HP2_STR_SLOTS - 1);
    for (unsigned probe = 0; probe < HP2_STR_SLOTS; probe++,
         slot = (slot + 1) & (HP2_STR_SLOTS - 1)) {
        hp2_str_slot_t* e = &hp2_strtab[slot];
        if (e->s == NULL) {
            e->s = s;
            e->idx = (uint32_t)hp2_str_emit(out, s);
            return e->idx;
        }
        if (e->s == s || strcmp(e->s, s) == 0)
            return e->idx;
    }
    return hp2_str_emit(out, s);             // full: duplicate, never ""
}

static uint32_t hp2_crc_table[256];

static uint32_t hp2_crc32(const unsigned char* p, size_t n) {
    if (hp2_crc_table[1] == 0)
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t c = i;
            for (int k = 0; k < 8; k++)
                c = (c & 1) ? 0xedb88320u ^ (c >> 1) : c >> 1;
            hp2_crc_table[i] = c;
        }
    uint32_t crc = 0xffffffffu;
    for (size_t i = 0; i < n; i++)
        crc = hp2_crc_table[(crc ^ p[i]) & 0xff] ^ (crc >> 8);
    return crc ^ 0xffffffffu;
}

static void hp2_write_gzip(FILE* f, const unsigned char* p, size_t n) {
    const unsigned char header[10] = { 0x1f, 0x8b, 8, 0, 0, 0, 0, 0, 0, 0xff };
    fwrite(header, 1, sizeof header, f);
    size_t at = 0;
    do {
        size_t chunk = n - at > 0xffff ? 0xffff : n - at;
        unsigned char bh[5];
        bh[0] = (at + chunk == n) ? 1 : 0;             // BFINAL, BTYPE=00
        bh[1] = chunk & 0xff;
        bh[2] = chunk >> 8;
        bh[3] = ~bh[1];
        bh[4] = ~bh[2];
        fwrite(bh, 1, sizeof bh, f);
        fwrite(p + at, 1, chunk, f);
        at += chunk;
    } while (at < n);
    uint32_t crc = hp2_crc32(p, n), isize = (uint32_t)n;
    unsigned char trailer[8] = {
        crc & 0xff, (crc >> 8) & 0xff, (crc >> 16) & 0xff, (crc >> 24) & 0xff,
        isize & 0xff, (isize >> 8) & 0xff, (isize >> 16) & 0xff, (isize >> 24) & 0xff,
    };
    fwrite(trailer, 1, sizeof trailer, f);
}

static void hp2_value_type(hp2_buf_t* out, unsigned field,
                           uint64_t type_idx, uint64_t unit_idx) {
    unsigned char tmp[24];
    hp2_buf_t sub = { tmp, 0, sizeof tmp, false };
    hp2_tag(&sub, 1, 0); hp2_varint(&sub, type_idx);
    hp2_tag(&sub, 2, 0); hp2_varint(&sub, unit_idx);
    hp2_submsg(out, field, &sub);
}

static bool hp2_dumped = false;

static void hp2_dump(void) {
    if (hp2_recs == NULL || hp2_dumped)
        return;
    hp2_dumped = true;
    yafl_heapprof_sample_enabled = false;
    hp2_lock();

    // Aggregate live records per stack slot, estimator-scaled: a sampled
    // object of size S was caught with probability ~(1 - e^(-S/rate)), so
    // it stands for 1/that objects of its site.
    uint32_t n_ids = yafl_prof_id_total();
    double* w_objs  = calloc(HP2_STACKS, sizeof(double));
    double* w_bytes = calloc(HP2_STACKS, sizeof(double));
    unsigned char* id_used = calloc(n_ids ? n_ids : 1, 1);
    hp2_buf_t out = { malloc(16u << 20), 0, 16u << 20, false };
    static unsigned char scratch_mem[64 << 10];
    if (w_objs == NULL || w_bytes == NULL || id_used == NULL || out.p == NULL) {
        free(w_objs); free(w_bytes); free(id_used); free(out.p);
        hp2_unlock();
        return;
    }
    uint64_t n_unknown = 0;
    double lost_objs = 0.0, lost_bytes = 0.0;
    for (uint32_t i = 0; i < HP2_RECORDS; i++) {
        uintptr_t key = atomic_load_explicit(&hp2_recs[i].addr, memory_order_relaxed);
        if (key <= HP2_TOMBSTONE)
            continue;
        uint32_t stack = hp2_recs[i].stack;
        double S = hp2_recs[i].bytes;
        double p = 1.0 - exp(-S / (double)hp2_rate);
        double w = p > 1e-9 ? 1.0 / p : 1.0;
        if (stack == UINT32_MAX) {
            // Stack lost to table limits: the BYTES still belong in the
            // profile. They aggregate under a bare (truncated) frame below
            // — understated attribution, never understated totals.
            n_unknown++;
            lost_objs += w;
            lost_bytes += S * w;
            continue;
        }
        w_objs[stack] += w;
        w_bytes[stack] += S * w;
        for (uint32_t j = 0; j < hp2_stacks[stack].len; j++) {
            uint32_t id = hp2_pool[hp2_stacks[stack].off + j];
            if (id < n_ids)
                id_used[id] = 1;
        }
    }

    hp2_strn = 0;
    hp2_str(&out, "");                       // index 0 is always ""
    uint64_t s_inobj  = hp2_str(&out, "inuse_objects");
    uint64_t s_count  = hp2_str(&out, "count");
    uint64_t s_inspc  = hp2_str(&out, "inuse_space");
    uint64_t s_bytes  = hp2_str(&out, "bytes");
    uint64_t s_space  = hp2_str(&out, "space");
    hp2_value_type(&out, 1, s_inobj, s_count);   // sample_type[0]
    hp2_value_type(&out, 1, s_inspc, s_bytes);   // sample_type[1]

    // Samples: one per stack with weight. Location ids are frame id + 1,
    // LEAF FIRST (the pool holds root first).
    for (uint32_t s = 0; s < HP2_STACKS; s++) {
        if (w_objs[s] == 0.0)
            continue;
        hp2_buf_t sub = { scratch_mem, 0, sizeof scratch_mem, false };
        hp2_buf_t packed = { scratch_mem + (48 << 10), 0, 16 << 10, false };
        for (uint32_t j = hp2_stacks[s].len; j > 0; j--)
            hp2_varint(&packed, (uint64_t)hp2_pool[hp2_stacks[s].off + j - 1] + 1);
        hp2_tag(&sub, 1, 2);
        hp2_varint(&sub, packed.n);
        hp2_put(&sub, packed.p, packed.n);
        packed.n = 0;
        hp2_varint(&packed, (uint64_t)(w_objs[s] + 0.5));
        hp2_varint(&packed, (uint64_t)(w_bytes[s] + 0.5));
        hp2_tag(&sub, 2, 2);
        hp2_varint(&sub, packed.n);
        hp2_put(&sub, packed.p, packed.n);
        if (!sub.overflow && !packed.overflow)
            hp2_submsg(&out, 2, &sub);
    }

    // Lost-stack residue: one sample under a bare (truncated) frame.
    if (lost_objs > 0.0) {
        uint32_t trunc_id = yafl_prof_reserved_id(YAFL_PROF_RES_TRUNCATED);
        if (trunc_id < n_ids)
            id_used[trunc_id] = 1;
        unsigned char tmp[48];
        hp2_buf_t sub = { tmp, 0, sizeof tmp, false };
        unsigned char ptmp[24];
        hp2_buf_t packed = { ptmp, 0, sizeof ptmp, false };
        hp2_varint(&packed, (uint64_t)trunc_id + 1);
        hp2_tag(&sub, 1, 2);
        hp2_varint(&sub, packed.n);
        hp2_put(&sub, packed.p, packed.n);
        packed.n = 0;
        hp2_varint(&packed, (uint64_t)(lost_objs + 0.5));
        hp2_varint(&packed, (uint64_t)(lost_bytes + 0.5));
        hp2_tag(&sub, 2, 2);
        hp2_varint(&sub, packed.n);
        hp2_put(&sub, packed.p, packed.n);
        hp2_submsg(&out, 2, &sub);
    }

    // One Location (with one Line) and one Function per used frame id.
    for (uint32_t id = 0; id < n_ids; id++) {
        if (!id_used[id])
            continue;
        const char* file;
        int32_t line;
        yafl_prof_id_srcloc(id, &file, &line);
        uint64_t s_name = hp2_str(&out, yafl_prof_id_name(id));
        uint64_t s_file = hp2_str(&out, file);

        unsigned char tmp[64];
        hp2_buf_t lin = { tmp, 0, sizeof tmp, false };
        hp2_tag(&lin, 1, 0); hp2_varint(&lin, (uint64_t)id + 1);
        hp2_tag(&lin, 2, 0); hp2_varint(&lin, (uint64_t)(line < 0 ? 0 : line));
        hp2_buf_t loc = { scratch_mem, 0, 128, false };
        hp2_tag(&loc, 1, 0); hp2_varint(&loc, (uint64_t)id + 1);
        hp2_submsg(&loc, 4, &lin);
        hp2_submsg(&out, 4, &loc);

        hp2_buf_t fn = { scratch_mem, 0, 256, false };
        hp2_tag(&fn, 1, 0); hp2_varint(&fn, (uint64_t)id + 1);
        hp2_tag(&fn, 2, 0); hp2_varint(&fn, s_name);
        hp2_tag(&fn, 3, 0); hp2_varint(&fn, s_name);
        hp2_tag(&fn, 4, 0); hp2_varint(&fn, s_file);
        hp2_tag(&fn, 5, 0); hp2_varint(&fn, (uint64_t)(line < 0 ? 0 : line));
        hp2_submsg(&out, 5, &fn);
    }

    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    hp2_tag(&out, 9, 0);                     // time_nanos
    hp2_varint(&out, (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec);
    hp2_value_type(&out, 11, s_space, s_bytes);   // period_type
    hp2_tag(&out, 12, 0);                    // period
    hp2_varint(&out, hp2_rate);

    if (!out.overflow) {
        FILE* f = fopen(hp2_path, "wb");
        if (f != NULL) {
            hp2_write_gzip(f, out.p, out.n);
            fclose(f);
            fprintf(stderr, "[HEAPPROF] wrote %s\n", hp2_path);
        }
    }
    if (hp2_dropped != 0 || n_unknown != 0)
        fprintf(stderr, "[HEAPPROF] table limits: %" PRIu64 " records dropped, "
                        "%" PRIu64 " live records with lost stacks "
                        "(insert fails: pool=%" PRIu64 " probe=%" PRIu64 ")\n",
                hp2_dropped, n_unknown,
                hp2_stack_fail_pool, hp2_stack_fail_probe);
    free(w_objs);
    free(w_bytes);
    free(id_used);
    free(out.p);
    hp2_unlock();
}

void yafl_heapprof_dump(void) {
    hp2_dump();
    if (hp_out != NULL) {
        fflush(hp_out);
        fclose(hp_out);
        hp_out = NULL;
    }
    yafl_heapprof_enabled = false;
}
