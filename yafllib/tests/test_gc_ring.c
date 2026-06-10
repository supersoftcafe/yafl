// GC hand-off stress test — simulates how IO objects are passed around: a FIXED
// population of objects that never disappears, only gets MOVED from holder to
// holder and, crucially, CARRIED across worker threads inside a task for a brief
// window where it lives only in that task's context (not in any rooted heap
// field of the data structure). Meanwhile we allocate throwaway strings as fast
// as we can so the collector is always mid-scan / mid-prune. If a carried or
// held object is ever invisible to the GC for an instant and gets reclaimed,
// the integrity check (or the runtime's own objects-bitmap assert) fires.
//
// Each carried/held object is ~13 KB — most of a 16 KB GC page — so every one
// sits on its own page and the page scanner/pruner has to deal with it directly
// while the small string garbage churns around it.
//
// This is NOT an allocation-throughput test: the big objects are allocated once
// and only relocated; the only churn is collectable strings, so the live set is
// tiny and the heap never needs to be large.
//
// Run single- then multi-threaded:
//   YAFL_THREADS=1 ./test_gc_ring
//   YAFL_THREADS=4 ./test_gc_ring

#include "../yafl.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef HOLDERS          // ring slots per group
#define HOLDERS 8
#endif
#ifndef CHAINS           // independent groups shuffled concurrently
#define CHAINS 4
#endif
#ifndef STEPS_PER_CHAIN  // hand-offs per group
#define STEPS_PER_CHAIN 50000
#endif
#ifndef STRINGS_PER_STEP // throwaway strings per hand-off (GC pressure)
#define STRINGS_PER_STEP 64
#endif
#ifndef BIG_FILL         // payload bytes — pushes each big object to ~13 KB
#define BIG_FILL 13000
#endif
#ifndef TIMEOUT_SECONDS
#define TIMEOUT_SECONDS 180
#endif

#define BIGS_PER_CHAIN HOLDERS   // population that circulates within a group

// ── layouts ───────────────────────────────────────────────────────────────────
struct holder {                  // ring slot; `held` is the field we mutate
    object_t  parent;
    object_t* next;
    object_t* held;              // a big object, or NULL when this slot is the gap
};

struct big {                     // the thing handed around — ~one page, no pointers
    object_t parent;
    int64_t  id;                 // 0..BIGS_PER_CHAIN-1 within its group
    int64_t  magic;             // == MAGIC ^ id; detects reuse/corruption
    char     fill[BIG_FILL];
};
#define MAGIC 0x5eedface12345678LL

struct ctx {                     // per-hand-off task closure (carries one big)
    object_t  parent;
    object_t* cursor;            // the currently-empty holder (the gap)
    object_t* carried;          // big object in transit between holders/threads
    int64_t   steps;
};

static vtable_t holder_vt = {
    .object_size = sizeof(struct holder), .array_el_size = 0,
    .object_pointer_locations = maskof(struct holder, .next) | maskof(struct holder, .held),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "ho_holder", .implements_array = VTABLE_IMPLEMENTS(0),
};
static vtable_t big_vt = {
    .object_size = sizeof(struct big), .array_el_size = 0,
    .object_pointer_locations = 0, .array_el_pointer_locations = 0,
    .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "ho_big", .implements_array = VTABLE_IMPLEMENTS(0),
};
static vtable_t ctx_vt = {
    .object_size = sizeof(struct ctx), .array_el_size = 0,
    .object_pointer_locations = maskof(struct ctx, .cursor) | maskof(struct ctx, .carried),
    .array_el_pointer_locations = 0, .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 1, .name = "ho_ctx", .implements_array = VTABLE_IMPLEMENTS(0),
};

// ── roots ─────────────────────────────────────────────────────────────────────
// Each group's ring head roots that group's holders (via next) and the big
// objects they currently hold. The single in-transit big per group is reached
// through the live task's ctx, not from here — exactly the path under test.
static object_t*                _heads[CHAINS];
static roots_declaration_func_t _prev_roots;
static void _ho_declare_roots(void(*declare)(object_t**)) {
    _prev_roots(declare);
    for (int i = 0; i < CHAINS; ++i) declare(&_heads[i]);
}

static fun_t        _exit_cont;
static atomic_int   _chains_remaining;
static atomic_bool  _finished;
static atomic_llong _total_steps;

static const char STR_PAD[64] = "the quick brown fox jumps over the lazy dog 0123456789 ABCDE";

static void burn_strings(void) {   // collectable garbage to keep the GC working
    for (int i = 0; i < STRINGS_PER_STEP; ++i) {
        GC_SAFE_POINT();   // loop backedge safe-point, as generated YAFL code has
        (void)string_from_bytes((uint8_t*)STR_PAD, (int)(8 + (i & 31)));
    }
}

static void check_big(object_t* o, const char* where) {
    if (object_get_vtable(o) != &big_vt) {
        fprintf(stderr, "test_gc_ring: CORRUPT (%s): big %p vtable=%s\n",
                where, (void*)o, o ? object_get_vtable(o)->name : "(null)");
        abort();
    }
    struct big* b = (struct big*)o;
    if (b->magic != (MAGIC ^ b->id)) {
        fprintf(stderr, "test_gc_ring: CORRUPT (%s): big id=%lld magic=%llx\n",
                where, (long long)b->id, (unsigned long long)b->magic);
        abort();
    }
}

// The carried big plus the bigs held around the ring must always be the full set
// {0 .. BIGS_PER_CHAIN-1}, each present exactly once — nothing lost or duplicated.
static void verify_group(struct ctx* ctx) {
    char seen[BIGS_PER_CHAIN]; memset(seen, 0, sizeof seen);
    check_big(ctx->carried, "carried");
    int n = 1; seen[((struct big*)ctx->carried)->id] = 1;
    struct holder* h = (struct holder*)ctx->cursor;
    for (int i = 0; i < HOLDERS; ++i, h = (struct holder*)h->next) {
        if (!h->held) continue;
        check_big(h->held, "held");
        int id = (int)((struct big*)h->held)->id;
        if (seen[id]) { fprintf(stderr, "test_gc_ring: duplicate big id=%d\n", id); abort(); }
        seen[id] = 1; n++;
    }
    if (n != BIGS_PER_CHAIN) {
        fprintf(stderr, "test_gc_ring: lost a big — found %d of %d\n", n, BIGS_PER_CHAIN);
        abort();
    }
}

static void do_step(struct ctx* ctx);
static object_t* do_step_cb(void* ctxv, object_t* task) { (void)task; do_step((struct ctx*)ctxv); return NULL; }

static void post_step(struct ctx* ctx) {
    object_t* task = task_create(NULL);
    task_on_complete(task, (fun_t){ .f = (void*)do_step_cb, .o = (object_t*)ctx });
    thread_work_post_parallel(task);   // hand the carried big to (possibly) another thread
}

static void do_step(struct ctx* ctx) {
    struct holder* gap = (struct holder*)ctx->cursor;   // currently empty
    object_t* carried = ctx->carried;

    // Drop the carried big into the gap, then pick up the next big from the
    // following holder — that big is now "in transit", reachable only via the
    // task ctx we build below until it lands in a holder again.
    GC_WRITE_BARRIER(gap->held, 1);
    gap->held = carried;

    struct holder* nextgap = (struct holder*)gap->next;
    object_t* picked = nextgap->held;
    GC_WRITE_BARRIER(nextgap->held, 1);
    nextgap->held = NULL;

    burn_strings();                         // force the collector to run
    atomic_fetch_add(&_total_steps, 1);

    if (ctx->steps <= 1) {
        // Put the last carried big back so the whole population sits in the ring,
        // then verify all BIGS_PER_CHAIN are present exactly once.
        GC_WRITE_BARRIER(nextgap->held, 1);
        nextgap->held = picked;
        char seen[BIGS_PER_CHAIN]; memset(seen, 0, sizeof seen);
        struct holder* h = (struct holder*)nextgap; int n = 0;
        for (int i = 0; i < HOLDERS; ++i, h = (struct holder*)h->next) {
            if (!h->held) continue; check_big(h->held, "final");
            int id = (int)((struct big*)h->held)->id;
            if (seen[id]) { fprintf(stderr, "test_gc_ring: final dup id=%d\n", id); abort(); }
            seen[id] = 1; n++;
        }
        if (n != BIGS_PER_CHAIN) { fprintf(stderr, "test_gc_ring: final lost %d/%d\n", n, BIGS_PER_CHAIN); abort(); }

        if (atomic_fetch_sub(&_chains_remaining, 1) == 1) {
            printf("test_gc_ring: OK chains=%d holders=%d big=%zuB total_steps=%lld\n",
                   CHAINS, HOLDERS, sizeof(struct big), (long long)atomic_load(&_total_steps));
            fflush(stdout);
            atomic_store(&_finished, true);
            ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
        }
        return;
    }

    struct ctx* next = (struct ctx*)object_create(&ctx_vt);
    GC_WRITE_BARRIER(next->cursor, 1);  next->cursor  = (object_t*)nextgap;  // the new gap
    GC_WRITE_BARRIER(next->carried, 1); next->carried = picked;             // in transit
    next->steps = ctx->steps - 1;
    verify_group(next);                     // full population still present?
    post_step(next);
}

// ── watchdog ────────────────────────────────────────────────────────────────
static void* _watchdog_main(void* arg) {
    (void)arg;
    struct timespec d; clock_gettime(CLOCK_REALTIME, &d); d.tv_sec += TIMEOUT_SECONDS;
    pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER; pthread_cond_t cv = PTHREAD_COND_INITIALIZER;
    pthread_mutex_lock(&mu);
    while (!atomic_load(&_finished))
        if (pthread_cond_timedwait(&cv, &mu, &d) == ETIMEDOUT) {
            fprintf(stderr, "test_gc_ring: WATCHDOG TIMEOUT after %ds at %lld steps\n",
                    TIMEOUT_SECONDS, (long long)atomic_load(&_total_steps));
            abort();
        }
    pthread_mutex_unlock(&mu);
    return NULL;
}

static object_t* build_group(void) {
    struct holder* hs[HOLDERS];
    for (int i = 0; i < HOLDERS; ++i) hs[i] = (struct holder*)object_create(&holder_vt);
    for (int i = 0; i < HOLDERS; ++i) {
        GC_WRITE_BARRIER(hs[i]->next, 1);
        hs[i]->next = (object_t*)hs[(i + 1) % HOLDERS];
    }
    // Fill holders[1..H-1] with bigs id 1..H-1; holders[0] is the starting gap.
    for (int i = 1; i < HOLDERS; ++i) {
        struct big* b = (struct big*)object_create(&big_vt);
        b->id = i; b->magic = MAGIC ^ (int64_t)i;
        GC_WRITE_BARRIER(hs[i]->held, 1);
        hs[i]->held = (object_t*)b;
    }
    return (object_t*)hs[0];
}

static void _entrypoint(object_t* self, fun_t continuation) {
    (void)self;
    _exit_cont = continuation;
    atomic_store(&_chains_remaining, CHAINS);
    pthread_t wd; pthread_create(&wd, NULL, _watchdog_main, NULL); pthread_detach(wd);

    printf("test_gc_ring: chains=%d holders=%d big=%zuB steps/chain=%d strings/step=%d\n",
           CHAINS, HOLDERS, sizeof(struct big), STEPS_PER_CHAIN, STRINGS_PER_STEP);
    fflush(stdout);

    for (int c = 0; c < CHAINS; ++c) {
        _heads[c] = build_group();
        struct big* b0 = (struct big*)object_create(&big_vt);   // big id 0 starts in transit
        b0->id = 0; b0->magic = MAGIC ^ 0;
        struct ctx* ctx = (struct ctx*)object_create(&ctx_vt);
        GC_WRITE_BARRIER(ctx->cursor, 1);  ctx->cursor  = _heads[c];   // holders[0] is the gap
        GC_WRITE_BARRIER(ctx->carried, 1); ctx->carried = (object_t*)b0;
        ctx->steps = STEPS_PER_CHAIN;
        post_step(ctx);
    }
}

int main(void) {
    _prev_roots = add_roots_declaration_func(_ho_declare_roots);
    thread_start(_entrypoint);
    return 0;
}
