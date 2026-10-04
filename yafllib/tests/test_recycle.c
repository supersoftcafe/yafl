// Compiler-directed recycling (object_recycle + the YAFL_RECYCLE fast path).
//
// Part 1, single-stepped (gc_debug_manual_mode): the runtime half of the
// contract — which slots are accepted, that the next same-size immutable
// allocation takes the slot back, and that a root scan (the moment a thread's
// bump pages join the collection pool) flushes the lists and retires every
// slot allocated before it. Part 2, free-running: a churn of recycled
// temporaries interleaved with a rooted live structure across many automatic
// cycles; the live structure must survive intact (run under YAFL_GC_POISON,
// so a reclaimed-but-reachable slot aborts the scanner).

#define YAFL_RECYCLE 1
#include "../yafl.h"
#include "callee_saved.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern bool gc_debug_manual_mode;
extern int  gc_debug_stage(void);
extern void gc_debug_step(void);
extern void gc_recycle_report(FILE *out);

enum { ST_IDLE = 1 };

struct small { object_t parent; intptr_t a, b; };                  // 1 slot
struct pair  { object_t parent; object_t *head; struct pair *next; intptr_t v; intptr_t pad[3]; };  // 2 slots
static vtable_t small_vt = {
    .object_size = sizeof(struct small), .array_el_size = 0,
    .object_pointer_locations = 0, .array_el_pointer_locations = 0,
    .functions_mask = 0, .array_len_offset = 0, .is_mutable = 0,
    .name = "rc_small", .implements_array = VTABLE_IMPLEMENTS(0),
};
static vtable_t small_mut_vt = {
    .object_size = sizeof(struct small), .array_el_size = 0,
    .object_pointer_locations = 0, .array_el_pointer_locations = 0,
    .functions_mask = 0, .array_len_offset = 0, .is_mutable = 1,
    .name = "rc_small_mut", .implements_array = VTABLE_IMPLEMENTS(0),
};
static vtable_t pair_vt = {
    .object_size = sizeof(struct pair), .array_el_size = 0,
    .object_pointer_locations = maskof_w(struct pair, .head, 0) | maskof_w(struct pair, .next, 0),
    .array_el_pointer_locations = 0,
    .functions_mask = 0, .array_len_offset = 0, .is_mutable = 0,
    .name = "rc_pair", .implements_array = VTABLE_IMPLEMENTS(0),
};
static struct small static_small = { { VTABLE_TAG_CONST(&small_vt) }, 1, 2 };

static object_t*                _slots[1];
static roots_declaration_func_t _prev;
static void _decl(void(*declare)(object_t**)) { _prev(declare); declare(&_slots[0]); }
static fun_t _exit_cont;
static int failures = 0;

#define CHECK(cond) do { if (!(cond)) { \
        fprintf(stderr, "test_recycle: FAIL line %d: %s\n", __LINE__, #cond); \
        failures++; } } while (0)

static void run_one_cycle(void) {
    int guard = 0;
    do {
        gc_debug_step();
        if (++guard > 100000) { fprintf(stderr, "cycle did not start\n"); abort(); }
    } while (gc_debug_stage() == ST_IDLE);
    while (gc_debug_stage() != ST_IDLE) {
        gc_debug_step();
        if (++guard > 1000000) { fprintf(stderr, "cycle did not finish\n"); abort(); }
    }
}

static unsigned pending(unsigned slots) { return gc_recycle_tl.count[slots - 1]; }

static void __attribute__((noinline)) part1_stepped(void) {
    CHECK(gc_recycle_tl.epoch != 0);

    // Reuse: the slot comes straight back, zeroed by object_new.
    struct small *a = object_new(&small_vt);
    a->a = 41; a->b = 42;
    object_recycle((object_t*)a);
    CHECK(pending(1) == 1);
    struct small *b = object_new(&small_vt);
    CHECK(b == a);
    CHECK(b->a == 0 && b->b == 0);
    CHECK(pending(1) == 0);

    // LIFO, and size classes are separate.
    struct small *c = object_new(&small_vt);
    struct small *d = object_new(&small_vt);
    object_recycle((object_t*)c);
    object_recycle((object_t*)d);
    struct pair *p = object_new(&pair_vt);
    CHECK((void*)p != (void*)c && (void*)p != (void*)d);
    CHECK(pending(1) == 2);
    CHECK(object_new(&small_vt) == (void*)d);
    CHECK(object_new(&small_vt) == (void*)c);

    // Rejected: static, NULL, tagged scalars, mutable, pinned.
    uint64_t before = gc_recycle_tl.pushed;
    object_recycle((object_t*)&static_small);
    object_recycle(NULL);
    object_recycle(integer_from_int32(7));
    struct small *m = object_new(&small_mut_vt);
    object_recycle((object_t*)m);
    struct small *pinned = object_new(&small_vt);
    object_pin((object_t*)pinned);
    object_recycle((object_t*)pinned);
    object_unpin((object_t*)pinned);
    CHECK(gc_recycle_tl.pushed == before);
    CHECK(pending(1) == 0);

    // A root scan retires everything allocated before it, and drops the
    // lists: the held slot is garbage the cycle may now sweep.
    struct small *old = object_new(&small_vt);
    struct small *held = object_new(&small_vt);
    object_recycle((object_t*)held);
    CHECK(pending(1) == 1);
    uint32_t epoch = gc_recycle_tl.epoch;
    run_one_cycle();
    CHECK(gc_recycle_tl.epoch != epoch);
    CHECK(pending(1) == 0);
    object_recycle((object_t*)old);            // its page now belongs to the pool
    CHECK(pending(1) == 0);
    struct small *fresh = object_new(&small_vt);
    CHECK(fresh != held);
    object_recycle((object_t*)fresh);          // born after the scan: fine
    CHECK(pending(1) == 1);
    CHECK(object_new(&small_vt) == fresh);

    // Poison mode: never reused; header and payload made unmistakable.
    gc_recycle_poison = true;
    uint8_t limit = gc_recycle_tl.limit;
    gc_recycle_tl.limit = 0;                 // what YAFL_RECYCLE_POISON sets up
    struct pair *q = object_new(&pair_vt);
    q->v = 99;
    object_recycle((object_t*)q);
    gc_recycle_poison = false;
    gc_recycle_tl.limit = limit;
    CHECK(pending(2) == 0);
    CHECK(strcmp(vtable_untag(((object_t*)q)->vtable)->name, "<recycled: use after free>") == 0);
    CHECK(vtable_untag(((object_t*)q)->vtable)->object_pointer_locations == 0);
    CHECK((uintptr_t)q->v == (uintptr_t)0xDEADBEEF0ull);
}

// Part 2: a rooted list of N pairs, rebuilt repeatedly by path copying the
// way a persistent structure is updated in place of a mutable one — every
// replaced node is dead the moment its copy exists, so it is recycled.
// Temporaries are recycled too. Automatic cycles run throughout.
enum { N = 64, ROUNDS = 40000 };

static struct pair* __attribute__((noinline)) build(void) {
    struct pair *list = NULL;
    for (intptr_t i = 0; i < N; ++i) {
        struct pair *n = object_new(&pair_vt);
        n->v = i;
        n->next = list;
        list = n;
    }
    return list;
}

// Returns a copy of `list` with node k's value incremented. Nodes before k
// are copied (their originals recycled — this code holds the only reference
// once the root has moved on); the tail from k+1 is shared, not copied.
static struct pair* __attribute__((noinline)) bump(struct pair *list, int k) {
    if (k == 0) {
        struct pair *n = object_new(&pair_vt);
        n->v = list->v + 1;
        n->next = list->next;
        object_recycle((object_t*)list);
        return n;
    }
    struct pair *rest = bump(list->next, k - 1);
    intptr_t v = list->v;
    object_recycle((object_t*)list);
    struct pair *n = object_new(&pair_vt);
    n->v = v;
    n->next = rest;
    return n;
}

static void __attribute__((noinline)) part2_churn(void) {
    gc_debug_manual_mode = false;
    struct pair *list = build();
    GC_WRITE_BARRIER(_slots[0], 1);
    _slots[0] = (object_t*)list;
    for (int r = 0; r < ROUNDS; ++r) {
        // Take the list out of the root first: from here this frame holds
        // the only reference, which is the precondition object_recycle needs.
        struct pair *cur = (struct pair*)_slots[0];
        GC_WRITE_BARRIER(_slots[0], 1);
        _slots[0] = NULL;
        struct pair *next = bump(cur, r % 8);
        GC_WRITE_BARRIER(_slots[0], 1);
        _slots[0] = (object_t*)next;
        // A temporary that dies at once, and some plain garbage so the
        // collector keeps cycling.
        struct small *t = object_new(&small_vt);
        t->a = r;
        object_recycle((object_t*)t);
        for (int g = 0; g < 4; ++g) (void)object_create(&small_vt);
    }
    intptr_t expect[N];
    for (int i = 0; i < N; ++i) expect[i] = N - 1 - i;
    for (int r = 0; r < ROUNDS; ++r) expect[r % 8] += 1;
    struct pair *it = (struct pair*)_slots[0];
    for (int i = 0; i < N; ++i, it = it->next) {
        CHECK(it != NULL);
        if (it == NULL) break;
        CHECK(vtable_untag(((object_t*)it)->vtable) == &pair_vt);
        CHECK(it->v == expect[i]);
    }
    CHECK(it == NULL);
    gc_recycle_report(stdout);
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    gc_debug_manual_mode = true;
    while (gc_debug_stage() == 0) usleep(1000);
    part1_stepped();
    part2_churn();
    if (failures == 0) printf("test_recycle: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(failures ? 1 : 0));
}

int main(void) {
    setenv("YAFL_HEAP_SIZE", "64m", 0);
    _prev = add_roots_declaration_func(_decl);
    thread_start(_entrypoint);
    return failures ? 1 : 0;
}
