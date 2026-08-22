// yafllib/prof.c — sampling profiler: exact call counters + sampled CPU time.
//
// See docs/profiling-design.md. The division of labour:
//
//   * Generated code (compiled with --profile) bumps a per-thread call counter
//     and maintains a per-thread shadow stack of function ids via the INLINE
//     fast paths in yafl.h. That is the profiler's only per-call cost.
//   * Each worker thread owns a CPU-time timer (CLOCK_THREAD_CPUTIME_ID,
//     SIGEV_THREAD_ID -> SIGPROF), so samples land on the thread that spent
//     the CPU and stop arriving while it is parked. IO threads never register,
//     never get a timer, and run no YAFL code.
//   * The signal handler does exactly ONE thing: hash-cons the current shadow
//     stack into a preallocated per-thread open-addressing table. Self time,
//     the folded flame-graph file and (later) call edges are all DERIVED from
//     those unique stacks at dump time, in ordinary non-signal code.
//
// Design rules, same spirit as log.c:
//   1. The handler never calls malloc, never takes a lock, and touches only
//      its own thread's block (found via the timer's sival_ptr).
//   2. Counters are plain u64 with a single writer (their own thread). The
//      exit dump reads them while workers may still be running; a boundary
//      increment may be missed. Documented, benign — the alternative is an
//      atomic RMW on every call.
//   3. Output goes to explicit files (callgrind.out.<pid> + .folded), written
//      with buffered stdio at exit, announced once on stderr.
//
// pthread_getattr_np-style precedent: this file opts into _GNU_SOURCE for
// gettid() and SIGEV_THREAD_ID; the rest of the runtime stays strict-POSIX.
#define _GNU_SOURCE
#include "prof.h"

#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

// Older glibc spells the sigevent thread-id member through an internal union;
// the POSIX-ish name appeared later. Map it if this libc predates the alias.
#ifndef sigev_notify_thread_id
#define sigev_notify_thread_id _sigev_un._tid
#endif

// ── capacities ──────────────────────────────────────────────────────────────
// All per-thread, all preallocated at thread registration so the handler
// never allocates. Sizes are generous for a self-compile-scale program and
// still small next to the YAFL heap: ~1.3 MiB per worker plus the counters.
enum {
    PROF_STACK_CAP = 4096,       // shadow-stack ids; deeper frames are counted,
                                 // not stored, and samples gain a (truncated) leaf
    PROF_TABLE_CAP = 32768,      // unique-stack slots (power of two, open addressing)
    PROF_PROBE_MAX = 32,         // linear-probe bound before the leaf fallback
    PROF_POOL_CAP  = 1 << 20,    // u32 id pool backing the stored stacks (4 MiB)
};

// ── per-thread block ────────────────────────────────────────────────────────
typedef struct {
    uint64_t hash;               // 0 = empty slot (hash is forced non-zero)
    uint32_t off;                // offset into the thread's id pool
    uint32_t len;
    uint64_t weight;             // samples, pre-weighted by 1 + overrun
} prof_slot_t;

typedef struct prof_thread_s {
    struct prof_thread_s* next;  // intrusive registry list (CAS push)
    timer_t     timer;
    bool        timer_armed;
    uint64_t*   counters;        // [n_ids] exact call counts, single writer
    uint32_t*   stack;           // [PROF_STACK_CAP] the shadow stack
    prof_slot_t* table;          // [PROF_TABLE_CAP] unique sampled stacks
    uint32_t*   pool;            // [PROF_POOL_CAP] backing ids for table entries
    uint32_t    pool_used;
    uint64_t*   leaf_self;       // [n_ids] overflow fallback: self weight by leaf —
                                 // constant-time, cannot fill, ancestry lost
    uint64_t    samples_degraded; // total weight that fell back to leaf_self
} prof_thread_t;

// ── globals ─────────────────────────────────────────────────────────────────
bool yafl_prof_enabled = false;                    // read by object.c gates
thread_local yafl_prof_tl_t yafl_prof_tl;          // the yafl.h fast-path TLS

static const yafl_prof_fn_t* _fns    = NULL;       // program descriptors [n_fns]
static uint32_t              _n_fns  = 0;
static uint32_t              _n_ids  = 0;          // n_fns + YAFL_PROF_RESERVED
static long                  _hz     = 997;        // YAFL_PROF_HZ; prime avoids lockstep
static char                  _out[512];            // callgrind path; folded = path + ".folded"
static _Atomic bool          _active = false;      // handler gate; cleared by dump
static _Atomic(prof_thread_t*) _threads = NULL;    // registry of every worker's block

static const char* _reserved_name(uint32_t reserved_id) {
    switch (reserved_id) {
        case YAFL_PROF_RES_GC:        return "(GC)";
        case YAFL_PROF_RES_SCAVENGE:  return "(scavenger)";
        case YAFL_PROF_RES_TRUNCATED: return "(truncated)";
        case YAFL_PROF_RES_RUNTIME:   return "(runtime)";
        default:                      return "(?)";
    }
}

static const char* _id_name(uint32_t id) {
    return id < _n_fns ? _fns[id].name : _reserved_name(id - _n_fns);
}

// ── the sampling handler ────────────────────────────────────────────────────
// Runs on the sampled thread itself, so the shadow stack it reads is its own:
// no cross-thread reads, no locks. Everything it touches is preallocated.

// Hash-cons one composed stack (ids[0..depth) plus an optional extra leaf)
// into the thread's table: FNV-1a, bounded linear probe, insert on first
// empty, accumulate on match. Returns false when the table, pool or probe
// bound is exhausted. Async-signal-safe: no allocation, no locks.
static bool _stack_insert(prof_thread_t* t, const uint32_t* ids, int32_t depth,
                          uint32_t extra, uint64_t weight) {
    uint32_t len = (uint32_t)depth + (extra != 0 ? 1u : 0u);
    uint64_t h = 0xcbf29ce484222325ull;
    for (int32_t i = 0; i < depth; i++) {
        h ^= ids[i];
        h *= 0x100000001b3ull;
    }
    if (extra != 0) {
        h ^= extra;
        h *= 0x100000001b3ull;
    }
    if (h == 0)
        h = 1;   // 0 means empty slot

    uint32_t mask = PROF_TABLE_CAP - 1;
    uint32_t slot = (uint32_t)h & mask;
    for (int probe = 0; probe < PROF_PROBE_MAX; probe++, slot = (slot + 1) & mask) {
        prof_slot_t* s = &t->table[slot];
        if (s->hash == 0) {
            if ((uint64_t)t->pool_used + len > PROF_POOL_CAP)
                return false;
            uint32_t off = t->pool_used;
            for (int32_t i = 0; i < depth; i++)
                t->pool[off + (uint32_t)i] = ids[i];
            if (extra != 0)
                t->pool[off + len - 1] = extra;
            s->off = off;
            s->len = len;
            s->weight = weight;
            // Publish the hash LAST: the dump thread scans this table while
            // workers may still be sampling, and a non-zero hash must imply a
            // fully-written slot.
            atomic_signal_fence(memory_order_release);
            s->hash = h;
            t->pool_used += len;
            return true;
        }
        if (s->hash == h && s->len == len) {
            bool same = true;
            for (uint32_t i = 0; i < (uint32_t)depth && same; i++)
                same = t->pool[s->off + i] == ids[i];
            if (same && extra != 0)
                same = t->pool[s->off + len - 1] == extra;
            if (same) {
                s->weight += weight;
                return true;
            }
        }
    }
    return false;
}

static void _prof_handler(int sig, siginfo_t* si, void* uctx) {
    (void)sig;
    (void)uctx;
    if (!atomic_load_explicit(&_active, memory_order_relaxed))
        return;
    // The timer carries its thread's block; anything else (a stray SIGPROF
    // from outside) has no block to charge and is ignored.
    if (si->si_code != SI_TIMER || si->si_value.sival_ptr == NULL)
        return;
    prof_thread_t* t = (prof_thread_t*)si->si_value.sival_ptr;

    // If delivery fell behind (overrun), each missed tick is one more sample's
    // worth of CPU that elapsed with (approximately) this same stack.
    uint64_t weight = 1;
#ifdef si_overrun
    if (si->si_overrun > 0)
        weight += (uint64_t)si->si_overrun;
#endif

    // Snapshot the interrupted frame's shadow stack. The release fence in
    // yafl_prof_enter pairs with this acquire: an sp we read here covers only
    // fully-stored elements.
    int32_t sp = atomic_load_explicit(&yafl_prof_tl.sp, memory_order_relaxed);
    atomic_signal_fence(memory_order_acquire);
    int32_t cap = yafl_prof_tl.cap;
    int32_t depth = sp < cap ? sp : cap;
    if (depth < 0)
        depth = 0;   // unbalanced leave would be a compiler bug; stay safe here

    // Compose the stored form: the stack itself, plus a synthetic leaf when it
    // was truncated (frames beyond cap) or empty (runtime dispatch code).
    uint32_t extra = 0;
    if (sp > cap)
        extra = _n_fns + YAFL_PROF_RES_TRUNCATED;
    else if (depth == 0)
        extra = _n_fns + YAFL_PROF_RES_RUNTIME;

    // Store the full stack; when the table or pool cannot take it (deep,
    // highly-distinct stacks at compiler scale — a c1 self-compile overflows
    // any bounded table), fall back to a per-leaf accumulator: constant time,
    // cannot fill, async-signal-safe by construction. The sample's SELF
    // attribution survives exactly — the flat profile stays complete and
    // unbiased — only its ancestry is lost from the folded view.
    const uint32_t* ids = yafl_prof_tl.stack;
    if (_stack_insert(t, ids, depth, extra, weight))
        return;
    uint32_t leaf = depth > 0 ? ids[depth - 1] : extra;
    t->leaf_self[leaf] += weight;
    t->samples_degraded += weight;
}

// ── initialisation ──────────────────────────────────────────────────────────
// Called from the generated main() BEFORE thread_start, so it precedes every
// gc_declare_thread (worker 0 included) and every YAFL function call.
EXPORT void yafl_prof_init(const yafl_prof_fn_t* fns, uint32_t n_fns) {
    if (yafl_prof_enabled)
        return;   // idempotent
    _fns   = fns;
    _n_fns = n_fns;
    _n_ids = n_fns + YAFL_PROF_RESERVED;

    const char* hz = getenv("YAFL_PROF_HZ");
    if (hz && *hz) {
        _hz = atol(hz);
        if (_hz < 0)     _hz = 0;       // 0 = counters only, no timers
        if (_hz > 10000) _hz = 10000;   // period floor 100us; the handler is
                                        // cheap but signals are not free
    }

    const char* file = getenv("YAFL_PROF_FILE");
    if (file && *file)
        snprintf(_out, sizeof _out, "%s", file);
    else
        snprintf(_out, sizeof _out, "callgrind.out.%d", (int)getpid());

    if (_hz > 0) {
        struct sigaction sa;
        memset(&sa, 0, sizeof sa);
        sa.sa_sigaction = _prof_handler;
        // SA_RESTART: the IO threads never receive SIGPROF (no timer, no YAFL
        // code), but a worker's rare direct syscalls should not see EINTR.
        sa.sa_flags = SA_SIGINFO | SA_RESTART;
        sigemptyset(&sa.sa_mask);
        sigaction(SIGPROF, &sa, NULL);
    }

    atomic_store(&_active, true);
    yafl_prof_enabled = true;
    // Same shape as atexit(gc_stats_report): catches every exit() path,
    // including error exits, without touching __exit__.
    atexit(yafl_prof_dump);
}

// ── per-thread registration ─────────────────────────────────────────────────
HIDDEN void yafl_prof_thread_init(void) {
    if (!yafl_prof_enabled || yafl_prof_tl.counters != NULL)
        return;

    prof_thread_t* t = calloc(1, sizeof *t);
    uint64_t*    counters  = calloc(_n_ids, sizeof *counters);
    uint32_t*    stack     = calloc(PROF_STACK_CAP, sizeof *stack);
    prof_slot_t* table     = calloc(PROF_TABLE_CAP, sizeof *table);
    uint32_t*    pool      = calloc(PROF_POOL_CAP, sizeof *pool);
    uint64_t*    leaf_self = calloc(_n_ids, sizeof *leaf_self);
    if (!t || !counters || !stack || !table || !pool || !leaf_self) {
        // Never fatal: the thread simply runs uninstrumented. Say so once.
        static _Atomic bool warned = false;
        if (!atomic_exchange(&warned, true))
            fprintf(stderr, "[yafl] profiler: out of memory registering a thread; "
                            "its activity will be missing from the profile\n");
        free(t); free(counters); free(stack); free(table); free(pool); free(leaf_self);
        return;
    }
    t->counters  = counters;
    t->stack     = stack;
    t->table     = table;
    t->pool      = pool;
    t->leaf_self = leaf_self;

    // Wire the fast-path TLS. From this point yafl_prof_enter on this thread
    // counts and pushes.
    yafl_prof_tl.counters = counters;
    yafl_prof_tl.stack    = stack;
    yafl_prof_tl.cap      = PROF_STACK_CAP;
    atomic_store_explicit(&yafl_prof_tl.sp, 0, memory_order_relaxed);

    // Register for the exit dump.
    t->next = atomic_load(&_threads);
    while (!atomic_compare_exchange_weak(&_threads, &t->next, t))
        ;

    if (_hz > 0) {
        struct sigevent sev;
        memset(&sev, 0, sizeof sev);
        sev.sigev_notify = SIGEV_THREAD_ID;
        sev.sigev_signo  = SIGPROF;
        sev.sigev_value.sival_ptr = t;
        sev.sigev_notify_thread_id = gettid();
        if (timer_create(CLOCK_THREAD_CPUTIME_ID, &sev, &t->timer) == 0) {
            long ns = 1000000000L / _hz;
            struct itimerspec its;
            its.it_interval.tv_sec  = ns / 1000000000L;
            its.it_interval.tv_nsec = ns % 1000000000L;
            its.it_value = its.it_interval;
            timer_settime(t->timer, 0, &its, NULL);
            t->timer_armed = true;
        } else {
            static _Atomic bool warned = false;
            if (!atomic_exchange(&warned, true))
                fprintf(stderr, "[yafl] profiler: timer_create failed (%s); "
                                "call counts only, no time samples\n", strerror(errno));
        }
    }
}

// ── pseudo-frames for runtime work ──────────────────────────────────────────
HIDDEN void yafl_prof_runtime_push(uint32_t reserved_id) {
    yafl_prof_enter(_n_fns + reserved_id);
}

HIDDEN void yafl_prof_runtime_pop(void) {
    yafl_prof_leave();
}

// ── exit dump ───────────────────────────────────────────────────────────────
// Workers may still be running: counters are read racily (documented above),
// and the sample tables are quiesced by disarming every timer and clearing
// _active first. A slot written concurrently with the disarm is either fully
// visible (hash published last) or ignored.

static void _write_callgrind(FILE* f, const uint64_t* counts, const uint64_t* self_ns) {
    fprintf(f, "# callgrind format\n");
    fprintf(f, "version: 1\n");
    fprintf(f, "creator: yafl --profile\n");
    fprintf(f, "pid: %d\n\n", (int)getpid());
    fprintf(f, "desc: Ns: sampled CPU nanoseconds (%ld Hz per-thread CPU-time timers, all threads summed)\n",
            _hz);
    fprintf(f, "desc: Calls: exact call count (compiler-emitted counters)\n\n");
    fprintf(f, "positions: line\n");
    fprintf(f, "events: Ns Calls\n\n");

    uint64_t total_ns = 0, total_calls = 0;
    for (uint32_t id = 0; id < _n_ids; id++) {
        if (counts[id] == 0 && self_ns[id] == 0)
            continue;   // never called, never sampled: keep the file small
        const char* file = id < _n_fns && _fns[id].file && _fns[id].file[0] ? _fns[id].file : "??";
        int32_t line = id < _n_fns ? _fns[id].line : 0;
        fprintf(f, "fl=%s\nfn=%s\n%d %llu %llu\n\n",
                file, _id_name(id), (int)line,
                (unsigned long long)self_ns[id], (unsigned long long)counts[id]);
        total_ns += self_ns[id];
        total_calls += counts[id];
    }
    fprintf(f, "summary: %llu %llu\n",
            (unsigned long long)total_ns, (unsigned long long)total_calls);
}

static void _write_folded(FILE* f) {
    // One line per unique (stack, thread) pair, weights in samples. Identical
    // stacks from different threads produce repeated lines; every folded-stack
    // consumer sums repeats, so cross-thread merging here would buy nothing.
    for (prof_thread_t* t = atomic_load(&_threads); t; t = t->next) {
        for (uint32_t i = 0; i < PROF_TABLE_CAP; i++) {
            const prof_slot_t* s = &t->table[i];
            if (s->hash == 0 || s->weight == 0)
                continue;
            for (uint32_t k = 0; k < s->len; k++)
                fprintf(f, "%s%s", k ? ";" : "", _id_name(t->pool[s->off + k]));
            fprintf(f, " %llu\n", (unsigned long long)s->weight);
        }
        // Overflow-fallback samples: ancestry lost, shown as (truncated);leaf.
        for (uint32_t id = 0; id < _n_ids; id++)
            if (t->leaf_self[id] > 0)
                fprintf(f, "%s;%s %llu\n",
                        _reserved_name(YAFL_PROF_RES_TRUNCATED), _id_name(id),
                        (unsigned long long)t->leaf_self[id]);
    }
}

HIDDEN void yafl_prof_dump(void) {
    if (!yafl_prof_enabled)
        return;
    if (!atomic_exchange(&_active, false))
        return;   // already dumped

    // Disarm every thread's timer (timer ids are process-wide, deletable from
    // here), then give any in-flight handler a moment to retire. _active is
    // already false, so a straggler that does run records nothing.
    uint64_t degraded = 0;
    for (prof_thread_t* t = atomic_load(&_threads); t; t = t->next) {
        if (t->timer_armed) {
            timer_delete(t->timer);
            t->timer_armed = false;
        }
        degraded += t->samples_degraded;
    }

    // Derive per-function totals: exact calls (merged counters) and self time
    // (leaf of each unique sampled stack, weight x sampling period).
    uint64_t* counts  = calloc(_n_ids, sizeof *counts);
    uint64_t* self_ns = calloc(_n_ids, sizeof *self_ns);
    if (!counts || !self_ns) {
        free(counts); free(self_ns);
        fprintf(stderr, "[yafl] profiler: out of memory at dump; profile lost\n");
        return;
    }
    uint64_t period_ns = _hz > 0 ? (uint64_t)(1000000000L / _hz) : 0;
    for (prof_thread_t* t = atomic_load(&_threads); t; t = t->next) {
        for (uint32_t id = 0; id < _n_ids; id++) {
            counts[id] += t->counters[id];
            // The overflow fallback: self weight whose ancestry was lost.
            self_ns[id] += t->leaf_self[id] * period_ns;
        }
        for (uint32_t i = 0; i < PROF_TABLE_CAP; i++) {
            const prof_slot_t* s = &t->table[i];
            if (s->hash == 0 || s->len == 0)
                continue;
            uint32_t leaf = t->pool[s->off + s->len - 1];
            self_ns[leaf] += s->weight * period_ns;
        }
    }

    FILE* cg = fopen(_out, "w");
    if (cg) {
        _write_callgrind(cg, counts, self_ns);
        fclose(cg);
    }
    char folded_path[sizeof _out + 8];
    snprintf(folded_path, sizeof folded_path, "%s.folded", _out);
    FILE* fd = fopen(folded_path, "w");
    if (fd) {
        _write_folded(fd);
        fclose(fd);
    }
    free(counts);
    free(self_ns);

    if (cg || fd)
        fprintf(stderr, "[yafl] profile written to %s (+ %s)\n", _out, folded_path);
    else
        fprintf(stderr, "[yafl] profiler: could not write %s: %s\n", _out, strerror(errno));
    if (degraded > 0)
        fprintf(stderr, "[yafl] profiler: %llu samples kept self-only as "
                        "(truncated);leaf — stack table/pool full\n",
                (unsigned long long)degraded);
}
