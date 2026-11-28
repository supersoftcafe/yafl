// The heap census counts an object marked from its own page (#134).
//
// The census adds an object's bytes on its first mark in the marker
// (docs/heap-profiling-design.md, layer 1). A claim marks the objects on the
// page it is scanning through a shortcut of its own (set in `seen`, scanned
// depth first), and that shortcut skipped the census: in an
// allocation-ordered chain, where almost every link is to the same page, the
// census saw only the links that cross a page.
//
//   1. A rooted, immutable chain of N small nodes, a few pages of them.
//   2. One full cycle (stepped), then the massif dump.
//   3. The node type's census must cover every node but the head (marked by
//      the root, which the census does not see).
//
// Run with YAFL_THREADS=1; uses gc_debug_manual_mode.

#include "../yafl.h"
#include "../gc_stage.h"
#include "../heapprof.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);

#define MASSIF_PATH "test_heapprof_chain.massif"
enum { N = 2000 };

struct node { object_t parent; struct node* next; char pad[16]; };   // one 32-byte slot
static vtable_t node_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = maskof(struct node, .next),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "heapprof_chain_node", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }
static fun_t _exit_cont;

static void fail(const char* what, long got) {
    fprintf(stderr, "test_heapprof_chain: FAIL %s (got %ld)\n", what, got);
    fflush(stderr);
    abort();
}

static void run_one_cycle(void) {
    int guard = 0;
    while (gc_debug_stage() == GC_STAGE_IDLE) {
        if (++guard > 100000) fail("cycle did not start", gc_debug_stage());
        gc_debug_step();
    }
    while (gc_debug_stage() != GC_STAGE_IDLE) {
        if (++guard > 1000000) fail("cycle did not finish", gc_debug_stage());
        gc_debug_step();
    }
}

static void __attribute__((noinline)) build(void) {
    struct node* head = NULL;
    for (int i = 0; i < N; ++i) {
        struct node* n = (struct node*)object_create(&node_vt);
        GC_STORE_IN(n, n->next, 1, head);
        head = n;
    }
    gc_root_overwrite(&_slots[0], 1);
    _slots[0] = (object_t*)head;
    gc_root_publish(&_slots[0], 1);
}

// The largest census of the node type in any snapshot.
static long node_bytes(void) {
    FILE* f = fopen(MASSIF_PATH, "r");
    if (f == NULL) fail("no massif file", 0);
    char line[512];
    long best = -1;
    while (fgets(line, sizeof line, f) != NULL) {
        long bytes;
        char name[128];
        if (sscanf(line, " n0: %ld 0x0: %127s", &bytes, name) == 2
                && strcmp(name, node_vt.name) == 0 && bytes > best)
            best = bytes;
    }
    fclose(f);
    return best;
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == GC_STAGE_NOT_STARTED) usleep(1000);   // wait for the collector
    while (gc_debug_stage() != GC_STAGE_IDLE) gc_debug_step();

    build();
    run_one_cycle();
    yafl_heapprof_dump();
    long bytes = node_bytes();
    long want = (long)(N - 1) * (long)sizeof(struct node);
    printf("test_heapprof_chain: censused %ld bytes of %d nodes (want at least %ld)\n",
           bytes, N, want);
    if (bytes < want) fail("the census missed nodes marked from their own page", bytes);
    unlink(MASSIF_PATH);
    printf("test_heapprof_chain: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    setenv("YAFL_HEAPPROF", MASSIF_PATH, 1);
    setenv("YAFL_PROF_HZ", "0", 1);
    unlink(MASSIF_PATH);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
