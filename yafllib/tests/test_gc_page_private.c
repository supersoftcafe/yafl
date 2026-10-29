// Deterministic, single-threaded test of the late store's inline privacy test
// (gc_store_is_settled_private, yafl.h): a page key compared with a thread
// key. The page's key is its nursery epoch until something leaves it; the
// thread's is its epoch until a shared store's value waits to escape.
//
//   1. Two fresh objects A and B on one nursery page both test private.
//   2. B escapes (rooted): A, on the same page, no longer tests private for
//      the inline store, although A itself has not escaped.
//   3. C, on a fresh page, tests private; a shared store leaves its value
//      pending, and C stops testing private until the pending slot is flushed.
//   4. C survives nursery collections: its page is promoted out of the nursery
//      and its key cleared.
//
// Manual mode holds the global collector IDLE, so no root scan moves the epoch
// on underneath: what changes the answer is only what each step does.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);

// Must match enum gc_stage in object.c.
enum { ST_IDLE = 1 };

struct node { object_t parent; object_t* f; };
static vtable_t node_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = maskof(struct node, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "pp_node", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];   // B
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }
static fun_t _exit_cont;

static void fail(const char* what) {
    fprintf(stderr, "test_gc_page_private: FAIL %s\n", what);
    fflush(stderr);
    abort();
}

static gc_page_t* page_of(object_t* o) {
    return (gc_page_t*)((uintptr_t)o & ~(uintptr_t)(GC_PAGE_SIZE - 1));
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);
    for (int g = 0; gc_debug_stage() != ST_IDLE; ++g) {
        if (g > 1000000) fail("stuck before IDLE");
        gc_debug_step();
    }
    for (int i = 0; !gc_alloc_tl.local_active; ++i) {
        if (i > 100000) fail("the nursery never started (run with it on)");
        volatile object_t* f = object_create(&node_vt);
        (void)f;
    }

    // (1) A and B on one page.
    object_t *a, *b;
    do { a = object_create(&node_vt); b = object_create(&node_vt); } while (page_of(a) != page_of(b));
    if (!gc_store_is_settled_private(a) || !gc_store_is_settled_private(b))
        fail("fresh nursery objects do not test private");

    // (2) B escapes; A's page goes with it.
    GC_ROOT_STORE(_slots[0], 1, b);
    if (gc_local_obj_private(b)) fail("rooting did not escape B");
    if (!gc_local_obj_private(a)) fail("A escaped with B");
    if (gc_store_is_settled_private(a)) fail("A still tests private on a page with an escapee");

    // (3) C on a fresh page; a shared store pending, then flushed.
    object_t* volatile c;
    do { c = object_create(&node_vt); } while (page_of(c) == page_of(a));
    if (!gc_store_is_settled_private(c)) fail("C does not test private");
    GC_STORE_IN(b, ((struct node*)b)->f, 1, NULL);   // B is shared: noted, pending
    if (gc_alloc_tl.pend_slot != &((struct node*)b)->f) fail("the store into B left no pending slot");
    if (gc_store_is_settled_private(c)) fail("C tests private with a store pending");
    gc_local_flush_pending();
    if (!gc_store_is_settled_private(c)) fail("C does not test private after the flush");

    // (4) C survives nursery collections (held by this stack frame): its page
    // is promoted out of the nursery.
    for (int i = 0; i < 400000; ++i) {
        volatile object_t* f = object_create(&node_vt);
        (void)f;
    }
    if (page_of(c)->head.local_epoch != 0) fail("C's page was not promoted (no nursery collection?)");
    if (page_of(c)->head.local_private != 0) fail("a promoted page kept its private key");
    if (gc_store_is_settled_private(c)) fail("C tests private after promotion");

    printf("test_gc_page_private: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
