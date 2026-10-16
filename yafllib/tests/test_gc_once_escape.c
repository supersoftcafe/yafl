// A value installed by yafl_cas_once into a shared object is reachable by
// other threads at once: readers of a write-once field take no pin. So when
// the owner then late-writes the value itself (a nested memoize), the value
// must test shared under that pin, or the late write skips its publication
// fence and a reader can see the new pointer before what it points at.
//
//   1. The nursery is active; O is born in it and escaped by rooting it.
//   2. V, fresh and private, is installed in O's write-once field.
//   3. V is late-pinned (object_pin_resolve): under the pin it must not test
//      private.
//
// The value's escape waits in the nursery's pending slot until a flush
// (gc_local_note_slot); the late pin is what must flush it.

#include "../yafl.h"
#include "../once.h"
#include <stdio.h>
#include <stdlib.h>

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

    // (1) The nursery starts at this thread's first refill.
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

    // (3) Late-pin V, as a nested yafl_cas_once does.
    object_t* pinned = object_pin_resolve(v);
    bool private_under_pin = gc_local_obj_private(pinned);
    object_unpin(pinned);
    if (private_under_pin) fail("a value other threads can read tests private under its late pin");

    printf("test_gc_once_escape: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
