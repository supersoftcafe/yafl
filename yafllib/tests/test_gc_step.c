// Deterministic, single-threaded reproduction of the lost-root-object bug.
//
// Hypothesis (single thread, single object): declared roots are scanned at
// gc_fsa_start — the START of the cycle — but a thread's stacks are scanned and
// its new pages are promoted LATER, in SCAN_ROOTS. So:
//
//   1. The cycle starts; the root slot _slots[0] is scanned while it is NULL.
//   2. We create object O and store it into _slots[0]. The root was already
//      scanned, so nothing marks O via it; the deletion write barrier only marks
//      the slot's OLD value (NULL). O lives on this thread's new_pages.
//   3. The stack is scanned and the new pages are promoted — O's page enters the
//      scan set, so O is now prunable this cycle. O is NOT on the stack (its only
//      reference is _slots[0], and we keep its address only in a plain global the
//      conservative scanner never looks at).
//   4. Mark finds nothing pointing at O (root already scanned, not on stack).
//   5. Prune reclaims O — even though _slots[0] still points to it.
//
// The test drives the GC FSA by hand (gc_debug_step) with allocation prevented
// from auto-advancing it (gc_debug_manual_mode), so the interleaving is exact.
// Run with YAFL_THREADS=1.

#include "../yafl.h"
#include <stdio.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed

// Must match enum gc_stage in object.c.
enum { ST_NOT_STARTED = 0, ST_IDLE = 1, ST_START = 2,
       ST_SCAN_ROOTS = 3, ST_MARK_SWEEP = 4, ST_PRUNE = 5 };

struct obj { object_t parent; object_t* f; };
static vtable_t obj_vt = {
    .object_size = sizeof(struct obj), .array_el_size = 0,
    .object_pointer_locations = maskof(struct obj, .f),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "step_obj", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[1];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }

// O's address is parked here — a plain global, which the GC does NOT scan, so the
// only GC-visible reference to O is the rooted _slots[0].
static volatile uintptr_t g_O;

static fun_t _exit_cont;

// Create O and publish it into the (already-scanned-this-cycle) root slot. Runs
// in its own frame and returns void, so O does not linger on the caller's stack.
static void create_and_store(void) {
    object_t* o = object_create(&obj_vt);
    GC_WRITE_BARRIER(_slots[0], 1);
    _slots[0] = o;
    g_O = (uintptr_t)o;
}

static void step_to(int target) {
    for (int g = 0; gc_debug_stage() != target; ++g) {
        if (g > 100000) { fprintf(stderr, "step_to: stuck at stage %d\n", gc_debug_stage()); abort(); }
        gc_debug_step();
    }
}

static int O_state(void) { return gc_debug_object_state((object_t*)g_O); }

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self;
    _exit_cont = cont;
    gc_debug_manual_mode = true;   // allocations no longer drive the FSA

    printf("test_gc_step: start stage=%d (IDLE=1)\n", gc_debug_stage());

    // (1) Drive to just-after gc_fsa_start: global roots scanned, _slots[0]==NULL.
    step_to(ST_SCAN_ROOTS);
    printf("test_gc_step: roots scanned; _slots[0]=%p\n", (void*)_slots[0]);

    // (2) Now create O and store into the (already-scanned) root.
    create_and_store();
    printf("test_gc_step: O=%p stored in _slots[0]; O_state=%d (1=live)\n",
           (void*)g_O, O_state());

    // (3) Finish SCAN_ROOTS: stack scan + promote new_pages (O's page enters scan set).
    step_to(ST_MARK_SWEEP);
    printf("test_gc_step: after stacks+promotion; O_state=%d\n", O_state());

    // (4) Mark.
    step_to(ST_PRUNE);
    printf("test_gc_step: after mark; O_state=%d\n", O_state());

    // (5) Prune.
    step_to(ST_IDLE);
    int st = O_state();
    printf("test_gc_step: after prune; O_state=%d; _slots[0]=%p (still points at O=%p)\n",
           st, (void*)_slots[0], (void*)g_O);

    if (st == 2)
        printf("test_gc_step: *** BUG: root-referenced object reclaimed ***\n");
    else
        printf("test_gc_step: object survived (state=%d)\n", st);
    fflush(stdout);

    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(st == 2 ? 7 : 0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
