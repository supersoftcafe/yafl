// A value installed by yafl_cas_once into a shared object is reachable by
// other threads at once: readers of a write-once field take no pin. So when
// the owner then late-writes into the value itself (a nested memoize), that
// write is a SHARED store: it must take its publication fence, or a reader can
// see the new pointer before what it points at.
//
//   1. The nursery is active; O is born in it and escaped by rooting it.
//   2. V, fresh and private, is installed in O's write-once field.
//   3. W is installed in V's field the same way, under V's late pin.
//
// The value's escape waits in the nursery's pending slot until a flush, so V
// still tests private when (3) begins. The store must not take that for
// private: it must flush first (gc_store_is_settled_private) and then note
// V's slot as a shared store's — what shows here as V escaped and V's slot
// now the pending one.

#include "../yafl.h"
#include "../once.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern int gc_debug_stage(void);

// One write-once pointer field, as a memoizing class has.
struct node { object_t parent; object_t* once; };
static vtable_t node_vt = {
    .object_size = sizeof(struct node), .array_el_size = 0,
    .object_pointer_locations = maskof(struct node, .once),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "once_node", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];   // O
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }
static fun_t _exit_cont;

static void fail(const char* what) {
    fprintf(stderr, "test_gc_once_escape: FAIL %s\n", what);
    fflush(stderr);
    abort();
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;

    // (1) The nursery is enabled when the collector starts, which waits for
    // every worker to register; this thread may get here first (a loaded
    // machine: tens of thousands of allocations). Then it starts at this
    // thread's next refill.
    while (gc_debug_stage() == 0) usleep(1000);
    for (int i = 0; !gc_alloc_tl.local_active; ++i) {
        if (i > 100000) fail("the nursery never started");
        volatile object_t* f = object_create(&node_vt);
        (void)f;
    }
    object_t* o = object_create(&node_vt);
    GC_ROOT_STORE(_slots[0], 1, o);
    if (gc_local_obj_private(o)) fail("rooting did not escape O");

    // (2) Install V.
    object_t* v = object_create(&node_vt);
    if (!gc_local_obj_private(v)) fail("a fresh nursery object is not private");
    yafl_cas_once(NULL, o, 0, 1, v);
    if (((struct node*)o)->once != v) fail("yafl_cas_once did not install V");

    // (3) Install W in V, as a nested yafl_cas_once does.
    if (gc_alloc_tl.pend_slot != &((struct node*)o)->once) fail("O's store left no pending slot");
    if (!gc_local_obj_private(v)) fail("V escaped before its pending slot was flushed");
    object_t* w = object_create(&node_vt);
    yafl_cas_once(NULL, v, 0, 1, w);
    if (((struct node*)v)->once != w) fail("yafl_cas_once did not install W");
    if (gc_local_obj_private(v)) fail("a value other threads can read was written as private");
    if (gc_alloc_tl.pend_slot != &((struct node*)v)->once)
        fail("the write into V was not noted as a shared store");

    printf("test_gc_once_escape: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
