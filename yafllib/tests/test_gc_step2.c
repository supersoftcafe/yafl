// Deterministic, single-threaded reproduction of the TRANSITIVE lost-object bug
// (root -> holder -> child), single-stepped.
//
// The point: with the declared-root scan now AFTER the stacks, an object stored
// directly into a root is safe. But a holder that is itself a brand-new object
// (its page not promoted this cycle) is MARKED yet never WALKED this cycle —
// because walking is page-driven and its page isn't in the scan set. So its
// child, which DID lose birth protection (its page was promoted this cycle), is
// pruned before the holder is ever walked.
//
// Forced interleaving (one thread, manual GC steps):
//   1. gc_fsa_start.
//   2. Create K (keeper, reachable via _slots[1]) and C (child) BEFORE promotion,
//      so their shared page is promoted this cycle. C's address is hidden in a
//      global; C is not otherwise referenced yet.
//   3. Step through promotion + the (after-stacks) root scan -> MARK_SWEEP.
//      K is marked via _slots[1]; C is not marked.
//   4. DURING MARK_SWEEP, create H on a fresh (unpromoted) page, set H->child=C,
//      and publish H into _slots[0]. The root scan already ran, so H is not
//      marked via the root; H is birth-protected (its page isn't promoted).
//   5. Finish mark, prune. C's page survives (K is seen), so C (unseen) is
//      reclaimed — even though _slots[0] -> H -> child == C.
//
// Run with YAFL_THREADS=1.

#include "../yafl.h"
#include <stdio.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern int  gc_debug_object_state(object_t* o);   // 0 not-heap, 1 live, 2 reclaimed

enum { ST_IDLE = 1, ST_SCAN_ROOTS = 3, ST_MARK_SWEEP = 4, ST_PRUNE = 5 };

struct holder { object_t parent; object_t* child; };
static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .child),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "step2_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
struct leaf { object_t parent; intptr_t pad; };
static vtable_t leaf_vt = {
    .object_size = sizeof(struct leaf), .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "step2_leaf", .implements_array = VTABLE_IMPLEMENTS(0),
};

static object_t*                _slots[2];   // [0] = holder, [1] = keeper
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) {
    _prev(declare);
    declare(&_slots[0]);
    declare(&_slots[1]);
}

static volatile uintptr_t g_C, g_H;   // addresses parked off-stack (GC never scans these)
static fun_t _exit_cont;

// Keeper K -> _slots[1], then child C right after it (same page), hidden in g_C.
static void make_keeper_and_child(void) {
    object_t* k = object_create(&leaf_vt);
    GC_WRITE_BARRIER(_slots[1], 1);
    _slots[1] = k;
    object_t* c = object_create(&leaf_vt);
    g_C = (uintptr_t)c;
}
// Holder H on a fresh page: H->child = C, publish H into _slots[0].
static void make_holder_link_publish(void) {
    struct holder* h = (struct holder*)object_create(&holder_vt);
    GC_WRITE_BARRIER(h->child, 1);
    h->child = (object_t*)g_C;
    GC_WRITE_BARRIER(_slots[0], 1);
    _slots[0] = (object_t*)h;
    g_H = (uintptr_t)h;
}

static void step_to(int t) {
    for (int g = 0; gc_debug_stage() != t; ++g) {
        if (g > 100000) { fprintf(stderr, "stuck at %d\n", gc_debug_stage()); abort(); }
        gc_debug_step();
    }
}
static int Cstate(void) { return gc_debug_object_state((object_t*)g_C); }
static int Hstate(void) { return gc_debug_object_state((object_t*)g_H); }

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;

    // (1) gc_fsa_start done; promotion + (after-stacks) root scan happen on the
    //     NEXT step. Create K and C now, before promotion.
    step_to(ST_SCAN_ROOTS);
    make_keeper_and_child();
    printf("test_gc_step2: created K(->_slots[1]) and C=%p (C only in a hidden global); C_state=%d\n",
           (void*)g_C, Cstate());

    // (2) Promotion (K & C's page enters scan set) + root scan (marks K, not C) -> MARK_SWEEP.
    step_to(ST_MARK_SWEEP);
    printf("test_gc_step2: promoted+root-scanned; C_state=%d (C unmarked, page in scan set)\n", Cstate());

    // (3) DURING mark: holder on a fresh unpromoted page; H->child=C; publish H.
    make_holder_link_publish();
    printf("test_gc_step2: created H=%p (fresh page), H->child=C, _slots[0]=H; H_state=%d C_state=%d\n",
           (void*)g_H, Hstate(), Cstate());

    // (4) Finish mark, then prune.
    step_to(ST_PRUNE);
    printf("test_gc_step2: after mark; C_state=%d\n", Cstate());
    step_to(ST_IDLE);

    int cs = Cstate(), hs = Hstate();
    printf("test_gc_step2: after prune; H_state=%d (1=live), C_state=%d (2=RECLAIMED); "
           "_slots[0]=%p H->child=%p C=%p\n",
           hs, cs, (void*)_slots[0],
           (void*)(_slots[0] ? ((struct holder*)_slots[0])->child : NULL), (void*)g_C);

    if (cs == 2 && hs == 1)
        printf("test_gc_step2: *** BUG: child reclaimed while root->holder->child still points at it ***\n");
    else
        printf("test_gc_step2: child survived (C_state=%d)\n", cs);
    fflush(stdout);

    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(cs == 2 ? 7 : 0));
}

int main(void) {
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return 0;
}
