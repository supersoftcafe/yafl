// test_gc_mesh: every worker mutates and reads a SHARED graph at once, within
// YAFL's sharing contract:
//   * a MUTABLE object other threads can reach is read and written only under
//     its pin (the lock) — here, the shared cells;
//   * an IMMUTABLE object's field may be read with no lock, and changes only
//     NULL -> value, once, under the pin (yafl_cas_once) — here, mailboxes.
// Nothing a lock-free reader can see is ever overwritten, which is what the
// collector's check-then-store deletion barrier relies on. (An earlier version
// overwrote cells that others read lock-free; it broke that contract and the
// barrier, rightly, did not cover it.)
//
// Aimed at weakly-ordered machines (aarch64): workers trade pointers through
// shared memory rather than locked task queues, so the collector's own
// ordering (escape barriers, forwarding, late-write handshakes, nursery
// publication) is what keeps objects alive.
//
// Each of W workers loops, and at every step does one of:
//   * BUILD   a fresh immutable chain (1..12 nodes, some ~0.5 KB, its tail
//             sometimes a chain another worker built) and PUBLISH it, or a
//             fresh empty mailbox, into one of its own cells;
//   * READ    any worker's cell, verify what it holds, and CARRY it on the
//             stack for a while;
//   * FILL    a mailbox read from any cell: write-once a chain into one of its
//             empty slots (late writes into pages that may already be old);
//   * STASH   a carried value into the worker's private mutable stash, which
//             ages into the old generation and keeps taking young pointers;
//   * ADOPT   a stash entry into one of its own cells, re-publishing a value
//             that was born in someone else's nursery.
// Between steps it churns garbage and passes a safe point. Every node carries
// a checksum over its id and its successor's checksum, so any reclaimed,
// poisoned (0x42), torn or mis-forwarded node anywhere on a chain is caught.
//
// Knobs: MESH_STEPS (per worker; env overrides the default), YAFL_THREADS, plus
// every YAFL_GC_* / YAFL_LOCAL_GC* setting. Run under YAFL_GC_POISON=1.

#include "../yafl.h"
#include "../once.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef MESH_STEPS
#define MESH_STEPS 200000
#endif
#define CELLS_PER_WORKER 8
#define MAX_W            64
#define NCELLS           (CELLS_PER_WORKER * MAX_W)
#define CARRY            4
#define STASH            8
#define MAILSLOTS        4
#define TIMEOUT_SECONDS  600

// ── layouts ──────────────────────────────────────────────────────────────────
struct node {                    // immutable chain link; 32 bytes
    object_t  parent;
    object_t* next;
    uint64_t  id;
    uint64_t  check;             // mix(id ^ next->check)
};
struct fat_node {                // same prefix, ~0.5 KB: spans many slots
    struct node n;
    uint64_t    pad[60];
};
struct mailbox {                 // immutable; slots go NULL -> chain once each
    object_t  parent;
    uint64_t  magic;
    object_t* slot[MAILSLOTS];   // the LAST pointer fields (yafl_cas_once addressing)
};
struct cell {                    // shared, mutable: accessed under its pin
    object_t  parent;
    object_t* val;               // a chain, a mailbox, or NULL
};
struct stash {                   // private, mutable, long-lived
    object_t  parent;
    object_t* s[STASH];
};
#define MAIL_MAGIC 0x6d61696c626f7821ULL

static vtable_t node_vt = {
    .object_size = sizeof(struct node), .object_pointer_locations = maskof(struct node, .next),
    .is_mutable = 0, .name = "mesh_node", .implements_array = VTABLE_IMPLEMENTS(0),
};
static vtable_t fat_vt = {
    .object_size = sizeof(struct fat_node), .object_pointer_locations = maskof(struct fat_node, .n.next),
    .is_mutable = 0, .name = "mesh_fat", .implements_array = VTABLE_IMPLEMENTS(0),
};
#define MAIL_MASK (((ptr_mask_t)((1u << MAILSLOTS) - 1)) << ptr_word_of(struct mailbox, .slot[0]))
static vtable_t mail_vt = {
    .object_size = sizeof(struct mailbox), .object_pointer_locations = MAIL_MASK,
    .is_mutable = 0, .name = "mesh_mailbox", .implements_array = VTABLE_IMPLEMENTS(0),
};
static vtable_t cell_vt = {
    .object_size = sizeof(struct cell), .object_pointer_locations = maskof(struct cell, .val),
    .is_mutable = 1, .name = "mesh_cell", .implements_array = VTABLE_IMPLEMENTS(0),
};
#define STASH_MASK (((ptr_mask_t)((1u << STASH) - 1)) << ptr_word_of(struct stash, .s[0]))
static vtable_t stash_vt = {
    .object_size = sizeof(struct stash), .object_pointer_locations = STASH_MASK,
    .is_mutable = 1, .name = "mesh_stash", .implements_array = VTABLE_IMPLEMENTS(0),
};

// ── roots: written once, before any worker starts ───────────────────────────
static object_t* _cells[NCELLS];
static object_t* _stashes[MAX_W];
static roots_declaration_func_t _prev_roots;
static void _mesh_declare_roots(void (*declare)(object_t**)) {
    _prev_roots(declare);
    for (int i = 0; i < NCELLS; ++i) declare(&_cells[i]);
    for (int i = 0; i < MAX_W; ++i) declare(&_stashes[i]);
}

static int          _workers;
static long         _steps;
static fun_t        _exit_cont;
static atomic_int   _next_id, _remaining;
static atomic_bool  _finished;
static atomic_llong _verified_nodes, _total_steps, _fills;

static inline uint64_t mix(uint64_t x) {
    x ^= x >> 33; x *= 0xff51afd7ed558ccdULL;
    x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ULL;
    return x ^ (x >> 33);
}
static inline uint32_t rnd(uint64_t* s) {
    *s ^= *s << 13; *s ^= *s >> 7; *s ^= *s << 17;
    return (uint32_t)(*s >> 16);
}

static NOINLINE void die(const char* what, int worker, object_t* root, object_t* at, int depth) {
    vtable_t* vt = at ? object_get_vtable(at) : NULL;
    fprintf(stderr, "test_gc_mesh: CORRUPT %s worker=%d root=%p node=%p depth=%d vtable=%p(%s)\n",
            what, worker, (void*)root, (void*)at, depth, (void*)vt,
            vt == &node_vt || vt == &fat_vt || vt == &mail_vt ? vt->name : "?");
    abort();
}

static inline bool is_node(object_t* p) {
    vtable_t* vt = p ? object_get_vtable(p) : NULL;
    return vt == &node_vt || vt == &fat_vt;
}

// Walk a chain end to end; every link must be a live node whose checksum
// agrees with its successor's.
static void verify_chain(object_t* chain, int worker, object_t* root) {
    int depth = 0;
    for (object_t* p = chain; p; p = ((struct node*)p)->next, ++depth) {
        vtable_t* vt = object_get_vtable(p);
        if (vt != &node_vt && vt != &fat_vt) die("bad vtable", worker, root, p, depth);
        struct node* n = (struct node*)p;
        uint64_t nc = n->next ? ((struct node*)n->next)->check : 0;
        if (n->check != mix(n->id ^ nc)) die("bad checksum", worker, root, p, depth);
        if (vt == &fat_vt && ((struct fat_node*)p)->pad[59] != n->check) die("bad fat tail", worker, root, p, depth);
        if (depth > 4096) die("cycle", worker, root, p, depth);
    }
    atomic_fetch_add_explicit(&_verified_nodes, depth, memory_order_relaxed);
}

// A value held in a cell, stash or carry slot: a chain or a mailbox. Mailbox
// slots are read lock-free (acquire pairs with yafl_cas_once's release).
static void verify(object_t* v, int worker) {
    if (v == NULL) return;
    if (object_get_vtable(v) == &mail_vt) {
        struct mailbox* m = (struct mailbox*)v;
        if (m->magic != MAIL_MAGIC) die("bad mailbox", worker, v, v, 0);
        for (int k = 0; k < MAILSLOTS; ++k)
            verify_chain(__atomic_load_n(&m->slot[k], __ATOMIC_ACQUIRE), worker, v);
        return;
    }
    verify_chain(v, worker, v);
}

static object_t* build(uint64_t* seed, object_t* tail) {
    object_t* head = tail;
    int len = 1 + (int)(rnd(seed) % 12);
    for (int i = 0; i < len; ++i) {
        bool fat = (rnd(seed) & 15) == 0;
        struct node* n = (struct node*)object_create(fat ? &fat_vt : &node_vt);
        n->next  = head;
        n->id    = ((uint64_t)rnd(seed) << 32) | rnd(seed);
        n->check = mix(n->id ^ (head ? ((struct node*)head)->check : 0));
        if (fat) ((struct fat_node*)n)->pad[59] = n->check;
        head = (object_t*)n;
    }
    return head;
}

static object_t* new_mailbox(void) {
    struct mailbox* m = (struct mailbox*)object_create(&mail_vt);
    m->magic = MAIL_MAGIC;
    return (object_t*)m;
}

// Cells are shared MUTABLE objects: both sides hold the pin. Mutable objects
// are never relocated, so the pinned copy is the cell itself.
static void publish(int cell, object_t* value) {
    struct cell* c = (struct cell*)object_pin_resolve(_cells[cell]);
    GC_WRITE_BARRIER_IN(c, c->val, 1);
    c->val = value;
    object_unpin((object_t*)c);
}
static object_t* take(int cell) {
    struct cell* c = (struct cell*)object_pin_resolve(_cells[cell]);
    object_t* v = c->val;
    object_unpin((object_t*)c);
    return v;
}

static void churn(uint64_t* seed) {
    static const char PAD[] = "mesh-churn-0123456789abcdefghijklmnopqrstuvwxyz";
    int n = 4 + (int)(rnd(seed) % 12);
    for (int i = 0; i < n; ++i) (void)str_from_bytes((const uint8_t*)PAD, 16 + (i & 15));
    if ((rnd(seed) & 3) == 0) (void)build(seed, NULL);   // dropped chains: pointer garbage
}

static void* _watchdog(void* arg) {
    (void)arg;
    struct timespec d; clock_gettime(CLOCK_REALTIME, &d); d.tv_sec += TIMEOUT_SECONDS;
    pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER; pthread_cond_t cv = PTHREAD_COND_INITIALIZER;
    pthread_mutex_lock(&mu);
    while (!atomic_load(&_finished))
        if (pthread_cond_timedwait(&cv, &mu, &d) == ETIMEDOUT) {
            fprintf(stderr, "test_gc_mesh: WATCHDOG TIMEOUT after %ds at %lld steps\n",
                    TIMEOUT_SECONDS, (long long)atomic_load(&_total_steps));
            abort();
        }
    pthread_mutex_unlock(&mu);
    return NULL;
}

static object_t* _worker(object_t* self, object_t* task) {
    (void)self; (void)task;
    int w = atomic_fetch_add(&_next_id, 1);
    uint64_t seed = mix(0x9e3779b97f4a7c15ULL * (uint64_t)(w + 1)) | 1;
    struct stash* st = (struct stash*)_stashes[w];
    object_t* volatile carried[CARRY] = { 0 };   // on the stack: conservatively scanned
    int ncells = _workers * CELLS_PER_WORKER;

    for (long step = 0; step < _steps; ++step) {
        GC_SAFE_POINT();
        uint32_t r = rnd(&seed) % 100;
        int mine = w * CELLS_PER_WORKER + (int)(rnd(&seed) % CELLS_PER_WORKER);
        if (r < 35) {                                        // BUILD + PUBLISH
            object_t* tail = carried[rnd(&seed) % CARRY];
            if ((rnd(&seed) & 1) || !is_node(tail)) tail = NULL;
            publish(mine, (rnd(&seed) % 4) == 0 ? new_mailbox() : build(&seed, tail));
        } else if (r < 60) {                                 // READ + CARRY
            object_t* v = take((int)(rnd(&seed) % (unsigned)ncells));
            verify(v, w);
            carried[rnd(&seed) % CARRY] = v;
        } else if (r < 75) {                                 // FILL a mailbox, write-once
            object_t* v = take((int)(rnd(&seed) % (unsigned)ncells));
            if (v && object_get_vtable(v) == &mail_vt) {
                object_t* tail = carried[rnd(&seed) % CARRY];
                if (!is_node(tail)) tail = NULL;
                object_t* chain = build(&seed, tail);
                int k = (int)(rnd(&seed) % MAILSLOTS);
                object_t* ok = yafl_cas_once(NULL, v, k, MAILSLOTS, chain);
                if (ok == integer_from_int32_noalloc(1))
                    atomic_fetch_add_explicit(&_fills, 1, memory_order_relaxed);
                verify(v, w);
                carried[rnd(&seed) % CARRY] = v;
            }
        } else if (r < 85) {                                 // STASH
            int k = (int)(rnd(&seed) % STASH);
            object_t* v = carried[rnd(&seed) % CARRY];
            GC_WRITE_BARRIER_IN(st, st->s[k], 1);
            st->s[k] = v;
        } else {                                             // ADOPT
            object_t* v = st->s[rnd(&seed) % STASH];
            verify(v, w);
            publish(mine, v);
        }
        churn(&seed);
        if ((step & 1023) == 0) {                            // everything I can reach
            for (int k = 0; k < CARRY; ++k) verify(carried[k], w);
            for (int k = 0; k < STASH; ++k) verify(st->s[k], w);
        }
        atomic_fetch_add_explicit(&_total_steps, 1, memory_order_relaxed);
    }

    for (int k = 0; k < CARRY; ++k) verify(carried[k], w);
    for (int k = 0; k < STASH; ++k) verify(st->s[k], w);
    if (atomic_fetch_sub(&_remaining, 1) == 1) {
        for (int i = 0; i < ncells; ++i)
            verify(take(i), -1);
        printf("test_gc_mesh: OK workers=%d steps/worker=%ld verified_nodes=%lld mailbox_fills=%lld\n",
               _workers, _steps, (long long)atomic_load(&_verified_nodes),
               (long long)atomic_load(&_fills));
        fflush(stdout);
        atomic_store(&_finished, true);
        ((void (*)(object_t*, object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
    }
    return NULL;
}

static void _entrypoint(object_t* self, fun_t continuation) {
    (void)self;
    _exit_cont = continuation;
    for (int i = 0; i < _workers * CELLS_PER_WORKER; ++i) {
        _cells[i] = object_create(&cell_vt);
        gc_root_publish(&_cells[i], 1);
    }
    for (int i = 0; i < _workers; ++i) {
        _stashes[i] = object_create(&stash_vt);
        gc_root_publish(&_stashes[i], 1);
    }
    atomic_store(&_remaining, _workers);
    pthread_t wd; pthread_create(&wd, NULL, _watchdog, NULL); pthread_detach(wd);
    printf("test_gc_mesh: workers=%d steps/worker=%ld\n", _workers, _steps);
    fflush(stdout);
    for (int i = 0; i < _workers; ++i) {
        object_t* t = task_create(NULL);
        task_on_complete(t, (fun_t){ .f = (void*)_worker, .o = NULL });
        thread_work_post_parallel(t);
    }
}

int main(void) {
    const char* e = getenv("YAFL_THREADS");
    long n = e && *e ? strtol(e, NULL, 10) : 4;
    _workers = (int)(n < 1 ? 1 : n > MAX_W ? MAX_W : n);
    char buf[8]; snprintf(buf, sizeof buf, "%d", _workers);
    setenv("YAFL_THREADS", buf, 1);   // one worker per mesh participant
    e = getenv("MESH_STEPS");
    _steps = e && *e ? strtol(e, NULL, 10) : MESH_STEPS;
    setenv("YAFL_HEAP_SIZE", "64m", 0);   // small: keeps the collector always busy
    _prev_roots = add_roots_declaration_func(_mesh_declare_roots);
    thread_start(_entrypoint);
    return 0;
}
