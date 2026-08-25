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
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <threads.h>
#include <time.h>
#include <unistd.h>

#include "yafl.h"

bool yafl_heapprof_enabled = false;

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

void yafl_heapprof_dump(void) {
    if (hp_out != NULL) {
        fflush(hp_out);
        fclose(hp_out);
        hp_out = NULL;
    }
    yafl_heapprof_enabled = false;
}
