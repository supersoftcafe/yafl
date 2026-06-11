/*
 * GC pressure test — a growing live set plus heavy churn must complete in a
 * small heap instead of aborting on allocation failure.
 *
 * Mimics the failure shape found by examples/yspell (immutable mergesort of a
 * 480k-word dictionary): a live structure that RATCHETS upward while garbage
 * is churned in bursts between safe-points. The live list grows to ~25% of the
 * heap; cumulative allocation is several times the heap. If the collector's
 * scheduling lets allocation outrun reclamation (in-cycle overshoot), the heap
 * fills and the runtime aborts — which is exactly what yspell did in any heap
 * under 1 GiB despite a ~30 MiB true live set.
 *
 * Build (against the debug runtime archive):
 *   clang -I yafllib -O0 -g yafllib/tests/test_gc_pressure.c \
 *       yafllib/build/debug-unix/libyafl.a -lpthread -lm -ldl -o /tmp/gc_pressure
 * Run:
 *   /tmp/gc_pressure        (heap size is set inside main)
 */

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>

struct node {
    object_t parent;        /* vtable pointer */
    struct node* next;      /* chain pointer — the GC must trace these */
    char payload[16];       /* → 32 bytes total */
};

static vtable_t node_vt = {
    .object_size                = sizeof(struct node),
    .array_el_size              = 0,
    .object_pointer_locations   = maskof(struct node, .next),
    .array_el_pointer_locations = 0,
    .functions_mask             = 0,
    .array_len_offset           = 0,
    .is_mutable                 = 0,
    .name                       = "node",
    .implements_array           = VTABLE_IMPLEMENTS(0),
};

static struct node* live_head;   /* root: the ratcheting live list */

static roots_declaration_func_t prev_roots;
static void declare_ring(void(*declare)(object_t**));
static void declare_roots(void(*declare)(object_t**)) {
    prev_roots(declare);
    declare((object_t**)&live_head);
    declare_ring(declare);
}

/* 64 MiB heap = 4096 pages. Live target: 768k nodes x 32 B = 24 MiB (~38%).
 * Two kinds of churn per outer iteration (one safe-point each, as codegen
 * emits on loop back-edges):
 *   - a burst of 64 immediately-dropped nodes, chained through each other so
 *     the scanner has real pointer work;
 *   - a MEDIUM-LIVED chain retired RING_SLOTS iterations later — like a merge
 *     pass's output that stays live until the next pass consumes it. This is
 *     the snapshot killer: it survives birth protection and one or more
 *     marking cycles before dying.
 * Total allocation ≈ 768k x (1+64+8) x 32 B ≈ 1.7 GiB through a 64 MiB heap. */
#define LIVE_NODES   (768 * 1024)
#define CHURN_PER    64
#define RING_CHAIN   8
#define RING_SLOTS   (16 * 1024)   /* medium-lived set ≈ 16k x 8 x 32 B = 4 MiB */

static struct node* ring[RING_SLOTS];

static void declare_ring(void(*declare)(object_t**)) {
    for (int i = 0; i < RING_SLOTS; i++)
        declare((object_t**)&ring[i]);
}

static void run_loop(object_t* unused, fun_t continuation) {
    (void)unused;
    for (long i = 0; i < LIVE_NODES; i++) {
        GC_SAFE_POINT();   /* one check-in per outer iteration, as codegen emits */

        /* Garbage burst: a dropped chain of CHURN_PER nodes. */
        struct node* chain = NULL;
        for (int j = 0; j < CHURN_PER; j++) {
            struct node* g = (struct node*)object_create(&node_vt);
            g->next = chain;
            g->payload[0] = (char)j;
            chain = g;
        }

        /* Medium-lived chain: replaces the slot written RING_SLOTS ago. */
        struct node* mid = NULL;
        for (int j = 0; j < RING_CHAIN; j++) {
            struct node* g = (struct node*)object_create(&node_vt);
            g->next = mid;
            g->payload[0] = (char)j;
            mid = g;
        }
        ring[i % RING_SLOTS] = mid;

        /* Ratchet the live set: prepend one node that survives forever. */
        struct node* keep = (struct node*)object_create(&node_vt);
        keep->next = live_head;
        keep->payload[0] = (char)i;
        live_head = keep;
    }

    /* Verify the live list is intact end to end. */
    long count = 0;
    for (struct node* p = live_head; p; p = p->next)
        count++;
    if (count != LIVE_NODES) {
        printf("FAIL: live list has %ld nodes, expected %d\n", count, LIVE_NODES);
        exit(1);
    }
    printf("survived: live %d nodes (%ld MiB), churned %ld MiB through a 64 MiB heap\n",
           LIVE_NODES, (long)LIVE_NODES * sizeof(struct node) / 1024 / 1024,
           (long)LIVE_NODES * (CHURN_PER + 1) * sizeof(struct node) / 1024 / 1024);
    fflush(stdout);
    fun_t k = continuation;
    ((void(*)(object_t*, object_t*))k.f)(k.o, INTEGER_LITERAL_1(0, 0));
}

int main(void) {
    /* Before any allocation: a heap small enough that scheduling slack, not
     * capacity, decides survival. Overridable for experiments. */
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_loop);
    return 0;
}
