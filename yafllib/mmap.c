
#include "yafl.h"   // must be first: sets the POSIX feature-test macros

#include <pthread.h>
#include <sys/mman.h>
#include <unistd.h>
#include <string.h>


EXPORT noreturn void abort_on_out_of_memory() {
    log_error_and_exit("Aborting due to memory allocation failure", stderr);
}

static noreturn void abort_on_invalid_size() {
    log_error_and_exit("Aborting due to malformed YAFL_HEAP_SIZE environment variable", stderr);
}



enum {
    PAGE_MARKER_FREE = 0,
    PAGE_MARKER_HEAD = 1,
    PAGE_MARKER_BODY = 2,
};

// Phase-1 scan budget: probe at most this many page positions before giving up
// and extending the watermark. Bounds allocation latency to a constant
// independent of heap size; in exchange the heap may inflate modestly under
// heavy fragmentation, then plateau as reuse catches up within the larger
// active region. Increase if profiling shows premature bumps; decrease if
// allocation latency dominates.
enum { MAX_SCAN_PROBES = 4096 };

// Scavenger tuning knobs (see memory_scavenge and the FREE-AGE comment below).
//
// SCAVENGE_EPOCH_SHIFT: the free-age epoch ticks once per 2^shift pages of
// cumulative allocation (8 → 256 pages = 4 MiB). SCAVENGE_FREE_AGE: a page
// must stay free across this many epochs — i.e. 32 MiB of allocation — to be
// returned to the OS. Denominated in allocation volume, NOT GC cycles or
// time: a cycle-based age silently rescaled when GC pacing changed (cycles
// per allocation dropped ~18x and findstr's buffer churn started bouncing
// off the kernel); a threshold worth less than a big file's own buffer also
// proved too weak (variable-size run demand reclaimed everything returned).
//
// SCAVENGE_HYSTERESIS: dead band (in pages) above the retain target. The warm
// slack oscillates as frees and claims interleave; without the band the
// scavenger trimmed each upward wiggle and the allocator faulted it straight
// back — a steady trickle-pump through the kernel.
// SCAVENGE_MIN_SPAN: only contiguous free spans at least this long are
// returned to the OS. Small holes between live pages are the allocator's
// natural working pool — returning them just made the next demand spike
// fault them straight back (measured on findstr: thousands of single pages
// bouncing while multi-page spans never did) — whereas a dead transient is
// by nature a long merged stretch. Undersized spans have their age stamp
// refreshed instead, so the walk does not even re-inspect them for another
// full age window.
enum {
    SCAVENGE_EPOCH_SHIFT = 8,
    SCAVENGE_FREE_AGE    = 8,
    SCAVENGE_HYSTERESIS  = 64,
    SCAVENGE_MIN_SPAN    = 8,
};

// Percentage of the pool's aged generation handed back each rotation;
// overridden by YAFL_GC_RELEASE_PCT in init(). See "The release rule" below.
// DEFAULT 10 (user, 08-15). Measured on a self-compile at 3G, madvise traffic
// rises steeply with the fraction while the frontier does not improve:
//   pct=0   198k pages returned, frontier 108,598
//   pct=10  667k                 frontier 104,381
//   pct=75  846k                 frontier 109,746
// so a small fraction keeps the rule live — surplus still decays away — without
// paying for it in churn on workloads whose demand is steady and which
// therefore have no surplus to find.
static unsigned pool_release_pct = 10;

// Saturating subtraction: the scan budgets must floor at zero, never wrap.
static inline size_t sat_sub(size_t x, size_t y) { return x > y ? x - y : 0; }


static pthread_once_t   pages_once = PTHREAD_ONCE_INIT;
static _Atomic(uint8_t)*pages_info = NULL;
static char*            pages_heap = NULL;
static size_t           total_page_count;       // Total mmap size of the heap allocation

// Heap bounds for the is-this-a-heap-pointer range check (declared in yafl.h):
// used by the GC's hot marking paths AND by vtable_is_forward — a vtable word
// holding a heap address is a compaction forwarding pointer, since real
// vtables are statics outside this range. Written once in init(); read racily
// thereafter — both are zero until then, rejecting everything, which is
// correct because no heap object can exist before the heap does.
EXPORT char*  _memory_heap_base  = NULL;
EXPORT size_t _memory_heap_bytes = 0;
static _Atomic(size_t)  upper_watermark = 0;    // Top of the SINGLES region (grows up from 0)
// Bottom of the RUNS region (grows DOWN from total_page_count). Fresh
// multi-page allocations claim below it; freed runs stay inside the band and
// are found by the top-down reuse scan. Singles and runs thus never
// interleave in address order: the virgin middle is consumed from both ends,
// and the contiguous windows large objects need survive at the top instead
// of being peppered with single pages the moment a bounded singles scan
// misses its probe budget (the self-host stage3 abort: no 83MB window
// despite gigabytes free). Initialised in init(); zero until then, which
// rejects nothing because no allocation exists before init either.
static _Atomic(size_t)  run_floor = 0;
static _Atomic(size_t)  alloc_count = 0;        // Track real heap usage
// Scavenger state: `pages_cold` marks pages returned to the OS (telemetry +
// no point advising twice); `scavenge_cursor` resumes the top-down walk
// across calls; the counters feed the GC stats line.
static _Atomic(uint8_t)*pages_cold = NULL;
static _Atomic(size_t)  cold_count = 0;          // pages currently cold (returned, not yet reused)
static size_t           scavenge_cursor = 0;     // only touched under the GC's fsa_lock
static _Atomic(size_t)  scavenge_returned  = 0;  // pages handed back to the OS
static _Atomic(size_t)  scavenge_reclaimed = 0;  // cold pages later re-claimed (churn signal)
static _Atomic(size_t)  scavenge_reclaimed_runs = 0;  // ...of which by multi-page claims

// FREE-AGE: each page is stamped with the scavenge epoch (one byte) at free
// time; the scavenger only returns pages whose stamp is at least
// SCAVENGE_FREE_AGE epochs old. The epoch is denominated in ALLOCATION
// VOLUME — it ticks once per 2^SCAVENGE_EPOCH_SHIFT pages ever claimed — so
// "aged" means "untouched across this much allocation", independent of how
// GC pacing maps cycles onto allocations (a cycle-denominated age silently
// rescaled when pacing changed, and churn returned). Pages the churn keeps
// reusing re-stamp on every free and never become eligible; a dead
// transient's pages are freed once and age out. Meaningful only because
// reuse is CONCENTRATED: the allocation cursors reset every epoch (see
// memory_pages_alloc), so the working set re-packs the same pages —
// singles lowest, runs highest — and everything between stops being touched
// and ages. With the old free-roaming next-fit ring, reuse was spread
// round-robin over the whole free pool and age was all-or-nothing. The byte
// wraps every 256 epochs: a very old free can transiently look young and
// merely returns an epoch later.
static _Atomic(uint8_t)*pages_free_epoch = NULL;
static _Atomic(size_t)  pages_ever = 0;   // cumulative pages claimed, drives the epoch
static inline uint8_t scavenge_epoch_now(void) {
    return (uint8_t)(atomic_load_explicit(&pages_ever, memory_order_relaxed)
                     >> SCAVENGE_EPOCH_SHIFT);
}

// Per-thread starting offset for the page scan. Begins at 0 so the first
// allocation by any thread packs near the bottom of the heap; concurrent
// threads disperse naturally via CAS losses on the page-marker bytes. Only
// ever read or written by its owning thread — no atomic, no cache-line
// contention.
static thread_local size_t alloc_cursor = 0;

// Last scavenge epoch this thread has observed; on change the singles cursor
// resets to the bottom so allocation re-packs the same pages every epoch —
// the concentration that lets untouched pages age. (Runs need no cursor:
// every run scan starts from the very top, see scan_runs_topdown.)
static thread_local uint8_t epoch_seen = 0;

// REUSE DIAGNOSTIC. A watermark bump is legitimate only when the heap really
// has no page to give. Measuring that needs the count of pages the allocator
// SHOULD have found: FREE, warm, and inside the singles band.
//
// Two wrong versions were tried first and are recorded so they are not tried
// again. Watermark arithmetic in a test is not it — whether a bump shows up in
// the delta depends on where the epoch boundary happens to fall, and the same
// scenario grew by 24 pages on a virgin heap and 0 inside the test binary with
// the defect present both times. "The scan exhausted its probe budget" is not
// it either: on any heap larger than the budget the scan nearly always stops
// early rather than completing a lap, so that counter reads ~87% whether or
// not a free page existed. It measures the scan, not the heap.
//
// So count the population directly. `singles_warm` is FREE ∧ warm ∧ below the
// watermark, maintained by the four transitions that can change it. Runs
// placed inside the singles band by the near-OOM whole-map scan are not
// tracked and would skew it slightly; that path runs only when the heap is
// otherwise full, where every bump is honest anyway.
// SIGNED, deliberately. The increment that publishes a page into the band and
// the decrement that claims it are not atomic with respect to each other: a
// scanner can claim a just-exposed page between our watermark CAS and our
// increment, decrementing first. Unsigned, that single transient wrapped the
// counter to ~2^64 and it never recovered — every reading after it was garbage.
static _Atomic(intptr_t) singles_warm = 0;  // FREE, warm, below the watermark
static _Atomic(size_t) scan_miss = 0;       // bounded singles scans that found nothing
static _Atomic(size_t) scan_miss_warm = 0;  // sum of singles_warm over those misses


static size_t get_size_of_heap() {
    const char* env_heap_size = getenv("YAFL_HEAP_SIZE");
    size_t heap_size;

    if (env_heap_size == NULL || !env_heap_size[0]) {
        heap_size = 1024ULL * 1024ULL * 1024ULL;
    } else {
        size_t len = strlen(env_heap_size);
        for (size_t index = 0; index + 1 < len; ++index) {
            char chr = env_heap_size[index];
            if (chr < '0' || chr > '9')
                abort_on_invalid_size();
        }

        size_t multiplier;
        switch (env_heap_size[len-1]) {
            case 'g': case 'G':
                multiplier = 1024ULL * 1024ULL * 1024ULL;
                break;
            case 'm': case '0': case '1': case '2': case '3': case '4':
            case 'M': case '5': case '6': case '7': case '8': case '9':
                multiplier = 1024ULL * 1024ULL;
                break;
            case 'k': case 'K':
                multiplier = 1024ULL;
                break;
            default:
                abort_on_invalid_size();
        }

        long long int number = atoll(env_heap_size);
        if (number <= 0)
            abort_on_invalid_size();

        heap_size = multiplier * (size_t)number;
    }

    return heap_size;
}


static void* allocate_lazy_heap(size_t size) {
    void *ptr = mmap(NULL, size + GC_PAGE_SIZE, PROT_READ | PROT_WRITE, MAP_ANONYMOUS | MAP_PRIVATE, -1, 0);
    if (ptr == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }
    return (void*)((((uintptr_t)ptr) + GC_PAGE_SIZE - 1) &~ (GC_PAGE_SIZE - 1));
}


static void init() {
    size_t heap_size = get_size_of_heap();

    total_page_count = heap_size / GC_PAGE_SIZE;

    pages_heap = allocate_lazy_heap(heap_size);
    pages_info = allocate_lazy_heap(total_page_count);
    pages_cold = allocate_lazy_heap(total_page_count);
    pages_free_epoch = allocate_lazy_heap(total_page_count);

    _memory_heap_base  = pages_heap;
    _memory_heap_bytes = heap_size;

    atomic_store_explicit(&run_floor, total_page_count, memory_order_relaxed);

    // YAFL_GC_RELEASE_PCT: percentage of the aged generation handed back each
    // rotation (see the release rule). 0 disables release entirely, which is
    // the pool-only arm; 100 is the plain rule with no dead band. A percentage
    // rather than a shift so the whole range is reachable, including both ends.
    const char *pct = getenv("YAFL_GC_RELEASE_PCT");
    if (pct != NULL && pct[0]) {
        long v = atol(pct);
        pool_release_pct = (unsigned)(v < 0 ? 0 : v > 100 ? 100 : v);
    }
}


// Tentatively claim [idx, idx+n): head first via CAS FREE→HEAD, then bodies via
// CAS FREE→BODY. On any per-cell collision, roll back the cells already taken
// and report failure. The partially built run is never observable as a live
// allocation because the caller has not yet seen the returned pointer; the GC
// only inspects pages it has been handed.
static bool try_claim_run(size_t idx, size_t n) {
    uint8_t expected = PAGE_MARKER_FREE;
    if (!atomic_compare_exchange_strong_explicit(
            &pages_info[idx], &expected, PAGE_MARKER_HEAD,
            memory_order_acq_rel, memory_order_relaxed))
        return false;

    for (size_t j = 1; j < n; ++j) {
        expected = PAGE_MARKER_FREE;
        if (!atomic_compare_exchange_strong_explicit(
                &pages_info[idx + j], &expected, PAGE_MARKER_BODY,
                memory_order_acq_rel, memory_order_relaxed)) {
            while (--j > 0)
                atomic_store_explicit(&pages_info[idx + j], PAGE_MARKER_FREE, memory_order_release);
            atomic_store_explicit(&pages_info[idx], PAGE_MARKER_FREE, memory_order_release);
            return false;
        }
    }
    return true;
}


// Phase 1 helper: scan within [0, snapshot) for a free run and claim it via the
// CAS chain. Returns the page index on success, SIZE_MAX on exhaustion.
//
// `step_budget` caps the number of page positions probed. The bound makes
// allocation latency O(step_budget) rather than O(snapshot).
//
// COLD-AVERSE unless `cold_ok`: a free window containing a scavenged page is
// skipped, so the cursor flows around returned memory and it stays returned —
// without this, the next-fit ring cyclically faulted cold pages back in while
// the scavenger re-returned the warm ones left behind (measured: ~12 pages/
// cycle bouncing at steady state). Cold skips are FREE with respect to the
// probe budget: they cost one byte-load, not a marker probe, and the warm
// pool typically sits behind a scavenged stretch the cursor must cross to
// reach it — budgeting the skips made the crossing fail and re-faulted a cold
// page per allocation. Termination on an all-cold heap comes from the
// one-full-lap bound instead. The first cold window seen is remembered as a
// FALLBACK and claimed if the scan finds no warm window: reusing returned
// memory beats inflating the watermark. The last-ditch near-OOM scan passes
// `cold_ok` and takes anything. The cold-bit loads are RELAXED by design:
// on a non-TSO machine a just-released cold page can transiently read warm,
// costing at worst one avoidable page fault — claimed_run's exchange keeps
// the accounting exact either way.
//
// On both success and budgeted failure, `alloc_cursor` is left pointing at the
// next position to inspect. On failure that means subsequent allocations
// continue the walk from where this one gave up — without this, a bounded
// scan that always restarts at 0 could repeatedly miss the same free region
// further along and bump the watermark indefinitely.
static size_t scan_within(size_t snapshot, size_t page_count, size_t step_budget, bool cold_ok) {
    if (snapshot < page_count)
        return SIZE_MAX;

    if (alloc_cursor + page_count > snapshot)
        alloc_cursor = 0;

    size_t i = alloc_cursor;
    size_t steps_remaining = snapshot < step_budget ? snapshot : step_budget;
    size_t lap_remaining = snapshot;   // hard bound: one full lap, free skips included
    size_t fallback = SIZE_MAX;

    while (steps_remaining > 0 && lap_remaining > 0) {
        if (i + page_count > snapshot) {
            i = 0;
            continue;  // wrap is a free operation, not a probe
        }

        if (atomic_load_explicit(&pages_info[i], memory_order_relaxed) != PAGE_MARKER_FREE) {
            i += 1;
            steps_remaining -= 1;
            lap_remaining -= 1;
            continue;
        }

        // Probe the rest of the window. If page i+j is not FREE, every window
        // starting in i+1..i+j would still include it, so we can skip the
        // cursor past the obstruction in one step rather than crawling.
        bool has_cold = !cold_ok
            && atomic_load_explicit(&pages_cold[i], memory_order_relaxed);
        size_t j = 1;
        while (j < page_count
                && atomic_load_explicit(&pages_info[i + j], memory_order_relaxed) == PAGE_MARKER_FREE) {
            has_cold = has_cold || (!cold_ok
                && atomic_load_explicit(&pages_cold[i + j], memory_order_relaxed));
            j += 1;
        }

        if (j < page_count) {
            size_t advance = j + 1;
            i += advance;
            steps_remaining = sat_sub(steps_remaining, advance);
            lap_remaining   = sat_sub(lap_remaining, advance);
            continue;
        }

        if (has_cold) {
            // Budget-free skip (see header comment); the lap bound terminates.
            if (fallback == SIZE_MAX)
                fallback = i;
            i += page_count;
            lap_remaining = sat_sub(lap_remaining, page_count);
            continue;
        }

        if (try_claim_run(i, page_count)) {
            alloc_cursor = i + page_count;
            return i;
        }

        // Lost the race for this window; nudge the cursor and try again.
        i += 1;
        steps_remaining -= 1;
        lap_remaining -= 1;
    }

    alloc_cursor = i;
    if (fallback != SIZE_MAX && try_claim_run(fallback, page_count)) {
        alloc_cursor = fallback + page_count;
        return fallback;
    }
    return SIZE_MAX;
}


// Top-down counterpart of scan_within, used for multi-page RUNS. Singles pack
// upward from the bottom, runs pack downward from the watermark: the two
// populations meet in the middle instead of peppering each other with holes,
// so the big contiguous spans large objects need survive at the top — and
// when a large transient dies, the scavenger's top-down walk finds its pages
// in one merged stretch.
//
// Every scan starts from the VERY TOP — runs keep no next-fit cursor. Runs
// are rare and large, so the skim over the live run band costs little, and
// the concentration is what keeps churned buffers warm: a freed span is
// re-claimed by the next run of similar size instead of being abandoned
// behind a descending cursor until it ages and the scavenger returns it
// (measured on findstr: a per-epoch cursor left ~10k pages/run bouncing
// through the kernel). Same probe-budget and cold-aversion contracts as
// scan_within (the fallback claim beats a watermark bump here too — and
// large runs land on cold spans often, since dead transients are exactly
// what the scavenger returns).
static size_t scan_runs_topdown(size_t floor, size_t page_count, size_t step_budget) {
    size_t span = total_page_count - floor;      // the runs band [floor, total)
    if (span < page_count)
        return SIZE_MAX;

    size_t top = total_page_count - page_count;  // highest legal window start
    size_t i = top;

    size_t steps_remaining = span < step_budget ? span : step_budget;
    size_t lap_remaining = span;   // hard bound: one full lap, free skips included
    size_t fallback = SIZE_MAX;

    while (steps_remaining > 0 && lap_remaining > 0) {
        // Probe the window [i, i+page_count) from its TOP end: an obstruction
        // at i+j rules out every window starting above i+j-page_count, so the
        // cursor can leap below it in one step — the mirror of scan_within's
        // skip-past-the-obstruction.
        bool has_cold = false;
        size_t j = page_count;
        while (j > 0
                && atomic_load_explicit(&pages_info[i + j - 1], memory_order_relaxed) == PAGE_MARKER_FREE) {
            has_cold = has_cold
                || atomic_load_explicit(&pages_cold[i + j - 1], memory_order_relaxed);
            j -= 1;
        }

        if (j == 0) {
            if (has_cold) {
                // Budget-free skip (see scan_within); the lap bound terminates.
                if (fallback == SIZE_MAX)
                    fallback = i;
                lap_remaining = sat_sub(lap_remaining, page_count);
                if (i < floor + page_count) break;   // band floor reached: nothing warm fits
                i -= page_count;
                continue;
            }
            if (try_claim_run(i, page_count))
                return i;
            // Lost the race for this window; nudge downward and try again.
            steps_remaining -= 1;
            lap_remaining -= 1;
            if (i == floor) break;           // band floor reached
            i -= 1;
            continue;
        }

        size_t obstruction = i + j - 1;
        size_t probed = page_count - j + 1;
        steps_remaining = sat_sub(steps_remaining, probed);
        lap_remaining   = sat_sub(lap_remaining, probed);
        if (obstruction < floor + page_count)
            break;                           // no window in the band fits below the obstruction
        i = obstruction - page_count;
    }

    if (fallback != SIZE_MAX && try_claim_run(fallback, page_count))
        return fallback;
    return SIZE_MAX;
}


// ── Per-thread page pool ─────────────────────────────────────────────────────
//
// A freed single page is remembered by the thread that freed it, so the next
// single-page allocation gets it for the price of a pop instead of a scan.
// The scan is BOUNDED (MAX_SCAN_PROBES), and once the live prefix is longer
// than that budget it stops reaching the free pages beyond it: measured on a
// self-compile, 62% of all watermark bumps (33,561 of 53,972) happened with a
// mean of 1,869 warm free pages sitting below the watermark. The abandoned
// pages are not lost — the scavenger hands them back to the OS — but that is
// the allocator and the scavenger undoing each other's work, and it cost 742
// MiB of madvise traffic over a 240 s slice with 55% of it faulted straight
// back in.
//
// THE POOL IS A HINT, NOT AN OWNER. A pooled page is FREE in `pages_info`,
// exactly as before, so:
//   * the conservative scanner still rejects it (memory_pages_is_alloc_head
//     tests the marker and never dereferences a free page),
//   * scan_runs_topdown can still claim it for a contiguous window — which is
//     what stops a growing pool from starving large runs, the failure that
//     once aborted the self-host on an 83 MB output string, and
//   * the scavenger can still return it.
// Anything that takes a pooled page leaves a STALE entry behind, detected at
// pop by the marker CAS failing. That is the whole of the coherence protocol:
// the marker array remains the single source of truth about who owns a page.
//
// Entries are page INDICES, not pointers into the pages themselves: an
// intrusive free list would put its links inside pages that a run scan or the
// scavenger may claim and overwrite at any moment, corrupting the list.
//
// Pools live in a STATIC ARRAY, never in thread-local storage, and are never
// reclaimed. Only worker threads reach the allocator, and that pool is fixed at
// startup and never exits — but a pool is not private to its thread: STEALING
// reads and writes it from every other worker. Tying a shared structure's
// lifetime to one thread's storage duration is the wrong coupling regardless of
// who is expected to exit, and it is not theoretical: an earlier version kept
// pools in thread_local storage with a registry of pointers into it, and the
// release cycle segfaulted the first time a thread that had allocated went
// away. A static slot is both simpler (no registry list) and outlives every
// participant by construction.
//
// Slots are claimed once per thread and never freed. Past the cap, threads
// share a slot by wrapping — safe, since the lock is what protects a pool, and
// sharing only costs contention.
enum { POOL_CHUNK_SLOTS = (GC_PAGE_SIZE - sizeof(void*) - sizeof(uint32_t)) / sizeof(uint32_t) };
enum { POOL_STEAL_BATCH = 32 };   // pages moved per steal: one victim-lock hold
                                  // per batch, not per page (the pool-lock
                                  // contention lesson, 2026-07-08)

typedef struct pool_chunk {
    struct pool_chunk *prev;
    uint32_t           count;
    uint32_t           slots[POOL_CHUNK_SLOTS];
} pool_chunk_t;

typedef struct pool_gen {
    pool_chunk_t *top;     // NULL when empty
    size_t        count;   // entries held, stale ones included
} pool_gen_t;

// TWO GENERATIONS. All page freeing happens during PRUNE, so at the moment one
// prune ends, every entry still in `aged` was put there by the PREVIOUS prune
// and has survived a whole GC cycle without any thread wanting it. That is the
// surplus, identified exactly rather than counted: no snapshot, no cross-thread
// arithmetic, one hook. `fresh` takes this prune's frees, and the two rotate at
// the prune tail (memory_pool_release_cycle).
//
// Allocation drains `aged` FIRST, so a page the mutator actually wanted is
// consumed before it can be mistaken for surplus — the release only ever sees
// what demand left behind.
enum { POOL_MAX_SLOTS = 256 };

typedef struct page_pool {
    _Atomic(bool)      lock;    // TTAS; the owner takes it too — a page op runs
                                // about once per 16 KiB allocated, so the
                                // uncontended CAS does not register
    pool_gen_t         aged;    // survived a full cycle unclaimed: the surplus
    pool_gen_t         fresh;   // freed during the current cycle
    pool_chunk_t      *spare;   // one emptied chunk kept back, so a pool
                                // oscillating across a chunk boundary does not
                                // allocate and free a chunk per page
} page_pool_t;

static page_pool_t     pool_slots[POOL_MAX_SLOTS];
static _Atomic(unsigned) pool_slots_used = 0;
static thread_local page_pool_t *pool_mine = NULL;
static thread_local unsigned     steal_from = 0;   // rotating victim cursor

// Pools that have ever been handed out. Read before iterating; a slot claimed
// after the read is simply missed this round, which costs nothing — its pages
// are judged next cycle.
static inline unsigned pool_count(void) {
    unsigned n = atomic_load_explicit(&pool_slots_used, memory_order_acquire);
    return n > POOL_MAX_SLOTS ? POOL_MAX_SLOTS : n;
}
static _Atomic(size_t) pool_hits   = 0;   // allocations served from the pool
static _Atomic(size_t) pool_steals = 0;   // ...of which taken from another thread
static _Atomic(size_t) pool_stale  = 0;   // entries dropped: page taken elsewhere

static void* memory_pages_alloc_raw(size_t page_count);
static void  memory_pages_free_raw(void* ptr, size_t page_count);
static bool  try_claim_run(size_t idx, size_t n);
static void* claimed_run(size_t idx, size_t page_count, bool was_free);

static inline void pool_lock(page_pool_t *p) {
    for (;;) {
        bool expected = false;
        if (atomic_compare_exchange_weak_explicit(&p->lock, &expected, true,
                                                  memory_order_acquire, memory_order_relaxed))
            return;
        do { __builtin_ia32_pause(); }
        while (atomic_load_explicit(&p->lock, memory_order_relaxed));
    }
}
static inline void pool_unlock(page_pool_t *p) {
    atomic_store_explicit(&p->lock, false, memory_order_release);
}

static page_pool_t* pool_self(void) {
    page_pool_t *p = pool_mine;
    if (UNLIKELY(p == NULL)) {
        unsigned slot = atomic_fetch_add_explicit(&pool_slots_used, 1, memory_order_acq_rel);
        pool_mine = p = &pool_slots[slot % POOL_MAX_SLOTS];
    }
    return p;
}

// Push under the caller's own lock. A chunk comes from the RAW allocator: the
// pooled path would re-enter this pool and deadlock on its own lock.
static void pool_push_locked(page_pool_t *pool, pool_gen_t *gen, uint32_t index) {
    pool_chunk_t *c = gen->top;
    if (c == NULL || c->count == POOL_CHUNK_SLOTS) {
        pool_chunk_t *empty = pool->spare;
        if (empty != NULL) {
            pool->spare = NULL;
        } else {
            empty = memory_pages_alloc_raw(1);
        }
        empty->prev  = c;
        empty->count = 0;
        gen->top = c = empty;
    }
    c->slots[c->count++] = index;
    gen->count++;
}

static bool pool_pop_locked(page_pool_t *pool, pool_gen_t *gen, uint32_t *out) {
    pool_chunk_t *c = gen->top;
    if (c == NULL)
        return false;
    *out = c->slots[--c->count];
    gen->count--;
    if (c->count == 0) {
        gen->top = c->prev;
        if (pool->spare == NULL) pool->spare = c;
        else                     memory_pages_free_raw(c, 1);
    }
    return true;
}

// Oldest first: a page the mutator wants should be consumed out of `aged`
// before the release can mistake it for surplus.
static bool pool_pop_any_locked(page_pool_t *pool, uint32_t *out) {
    return pool_pop_locked(pool, &pool->aged, out)
        || pool_pop_locked(pool, &pool->fresh, out);
}

// Pop entries until one can actually be claimed. The CAS is taken OUTSIDE the
// pool lock: it can fail (a run scan or the scavenger got there first) and
// retrying must not hold a pool against its owner.
//
// Cold entries are dropped rather than claimed. A cold page has been returned
// to the OS, and taking it back would fault it in for no reason — the pool
// would quietly undo the scavenger's work, which is the very churn it exists
// to stop. Dropping leaves it returned and reachable by the scan's own
// cold-fallback path if the heap ever genuinely needs it.
static void* pool_claim_from(page_pool_t *pool) {
    for (;;) {
        uint32_t index;
        pool_lock(pool);
        bool got = pool_pop_any_locked(pool, &index);
        pool_unlock(pool);
        if (!got)
            return NULL;
        if (atomic_load_explicit(&pages_cold[index], memory_order_relaxed)
                || !try_claim_run(index, 1)) {
            atomic_fetch_add_explicit(&pool_stale, 1, memory_order_relaxed);
            continue;
        }
        return claimed_run(index, 1, true);
    }
}

// Move up to POOL_STEAL_BATCH entries from a victim into this thread's pool,
// then serve from our own. Batched so a thread whose pool has run dry does not
// take the victim's lock once per page.
static bool pool_steal_batch(page_pool_t *self, page_pool_t *victim) {
    uint32_t taken[POOL_STEAL_BATCH];
    unsigned n = 0;
    pool_lock(victim);
    while (n < POOL_STEAL_BATCH && pool_pop_any_locked(victim, &taken[n]))
        n++;
    pool_unlock(victim);
    if (n == 0)
        return false;
    // Stolen pages land in `aged`: they are already at least as old as the
    // victim's oldest, and putting them in `fresh` would reset their age and
    // hide surplus from the release for another whole cycle.
    pool_lock(self);
    for (unsigned k = 0; k < n; ++k)
        pool_push_locked(self, &self->aged, taken[k]);
    pool_unlock(self);
    atomic_fetch_add_explicit(&pool_steals, n, memory_order_relaxed);
    return true;
}

// Own pool first, then steal. Returns NULL only when no thread holds a
// claimable page, which is when a scan — and possibly a bump — is honest.
static void* pool_take(void) {
    page_pool_t *self = pool_self();
    void *p = pool_claim_from(self);
    if (p != NULL) {
        atomic_fetch_add_explicit(&pool_hits, 1, memory_order_relaxed);
        return p;
    }

    // Walk the slots from where the last steal left off, so N dry threads do
    // not all drain the same victim. One full lap, then give up.
    unsigned n = pool_count();
    for (unsigned i = 0; i < n; ++i) {
        unsigned slot = (steal_from + i) % n;
        page_pool_t *v = &pool_slots[slot];
        if (v == self || !pool_steal_batch(self, v))
            continue;
        steal_from = slot;
        p = pool_claim_from(self);
        if (p != NULL) {
            atomic_fetch_add_explicit(&pool_hits, 1, memory_order_relaxed);
            return p;
        }
    }
    return NULL;
}

// Remember a freed single page. Runs are not pooled: they are rare (23 bumps
// over a 240 s self-compile), they need a size-matched structure the pool does
// not have, and leaving them to the banded top-down scan keeps the contiguity
// story exactly as it was.
static void pool_give(void* ptr) {
    ptrdiff_t offset = ((char*)ptr - pages_heap) / GC_PAGE_SIZE;
    // A uint32 index spans 2^32 pages — 64 TiB at GC_PAGE_SIZE — so the cast
    // cannot lose a heap anyone can configure; assert rather than assume.
    assert(offset >= 0 && (size_t)offset < total_page_count);
    page_pool_t *self = pool_self();
    pool_lock(self);
    pool_push_locked(self, &self->fresh, (uint32_t)offset);
    pool_unlock(self);
}

// ── The release rule ─────────────────────────────────────────────────────────
//
// At the end of each prune, hand back most of what went a whole GC cycle
// without anyone wanting it, and rotate the generations. That surplus is a
// MEASUREMENT of unmet-demand-that-never-came, which is what makes this
// self-calibrating; every term it replaces was a constant against a floating
// quantity. `retain = max(young*3, 256)` was measured 3x LARGER than the entire
// free pool on test_gc_pressure — 278 of 278 scavenge calls returned nothing
// while 30 MiB sat idle to process exit — and too small on the self-compile,
// where 55% of everything returned was faulted straight back in. One constant,
// wrong in both directions, because it was never measuring the thing it was
// deciding about.
//
// FRACTION, not all of it. Releasing every aged page has no dead band: any
// per-cycle wobble in demand converts one-for-one into madvise + fault. Keeping
// a slice makes the pool decay geometrically toward the working set instead of
// stepping off a cliff, and costs nothing in steady state, where `aged` is
// empty anyway because demand consumed it. YAFL_GC_RELEASE_PCT selects it:
// 0 disables release entirely (the pool-only arm), 100 is the plain rule, and
// the default is 10 (see the declaration for the measurements behind that).
// (pool_release_pct itself is declared up with the other tunables, because
// init() reads its environment override.)
static _Atomic(size_t) pool_released = 0;   // pages handed back by this path
static _Atomic(size_t) pool_retained = 0;   // ...kept back as the dead band
static _Atomic(size_t) pool_lost     = 0;   // aged entries claimed before we could

// Hand a contiguous span back. Deliberately NOT scavenge_release: that one
// keeps spans under SCAVENGE_MIN_SPAN warm, because it is guessing at idleness
// from span length. Here idleness is not a guess — the page went a whole GC
// cycle with every thread free to take it and none did — so span length has no
// say. (At GC_PAGE_SIZE a single page is already four host pages, well above
// madvise granularity.) Cold bit and counter go BEFORE the FREE store: the
// instant the marker reads FREE an allocator may claim it, and claimed_run's
// exchange-and-decrement must find them already in place.
static void pool_madvise_span(size_t lo, size_t end) {
    if (end == lo)
        return;
    madvise(pages_heap + lo * GC_PAGE_SIZE, (end - lo) * GC_PAGE_SIZE, MADV_DONTNEED);
    for (size_t k = lo; k < end; ++k) {
        atomic_store_explicit(&pages_cold[k], 1, memory_order_relaxed);
        atomic_fetch_add_explicit(&cold_count, 1, memory_order_relaxed);
        atomic_store_explicit(&pages_info[k], PAGE_MARKER_FREE, memory_order_release);
    }
    atomic_fetch_add_explicit(&scavenge_returned, end - lo, memory_order_relaxed);
}

// Drain a gathered batch: claim what is still ours, release it in ADDRESS ORDER
// so adjacent pages merge into one madvise, and account for every entry either
// way. Returns released via *out_released and entries lost to a concurrent
// claimant via *out_lost; the two must together account for every entry.
static void pool_release_batch(uint32_t *idx, size_t n,
                               size_t *out_released, size_t *out_lost) {
    // Insertion sort: n is the batch bound, and the array is near-sorted in
    // practice because frees follow the prune's own page order.
    for (size_t i = 1; i < n; ++i) {
        uint32_t v = idx[i];
        size_t j = i;
        while (j > 0 && idx[j-1] > v) { idx[j] = idx[j-1]; j--; }
        idx[j] = v;
    }
    size_t released = 0, lost = 0, run_lo = 0, run_end = 0;
    for (size_t i = 0; i < n; ++i) {
        uint32_t k = idx[i];
        // Already returned to the OS by the age-based scavenger: there is
        // nothing to hand back, and it left the warm population when it went
        // cold. Claiming it here would fault it in only to advise it away
        // again, and the unconditional decrement below would take a page out
        // of singles_warm twice — which underflowed the counter to ~2^64 on
        // the first -O3 run.
        if (atomic_load_explicit(&pages_cold[k], memory_order_relaxed)) {
            lost++;
            continue;
        }
        // Claim it back. Failure means a run scan or the scavenger took it
        // while it sat in the list: it is in use again, which is a correct
        // outcome — counted, never silently dropped.
        if (!try_claim_run(k, 1)) {
            lost++;
            continue;
        }
        atomic_fetch_sub_explicit(&singles_warm, 1, memory_order_relaxed);
        if (run_end != 0 && k == run_end) {
            run_end = k + 1;                  // extend the pending span
        } else {
            pool_madvise_span(run_lo, run_end);
            run_lo = k; run_end = k + 1;
        }
        released++;
    }
    pool_madvise_span(run_lo, run_end);
    atomic_fetch_add_explicit(&pool_lost, lost, memory_order_relaxed);
    *out_released = released;
    *out_lost     = lost;
}

// Called from the PRUNE tail, under fsa_lock with no concurrent executors —
// the same exclusive moment the scavenger has always used, so the transient
// HEAD marker stays invisible to the conservative scanner.
//
// The drain is TOTAL: it loops until the gathered generation is empty, bounded
// by how much there is rather than by a per-call page budget. A budget here is
// indistinguishable from forgetting, and leaves the caller unable to say
// whether what was scheduled actually went back.
EXPORT void memory_pool_release_cycle(void) {
    enum { BATCH = 256 };
    uint32_t batch[BATCH];

    // THE CLOCK IS ALLOCATION VOLUME, NOT CYCLES. Rotating once per GC cycle
    // was measured catastrophic: a cycle is about 30 pages of allocation on a
    // self-compile (935k cycles over 28M page claims), so "unused for a whole
    // cycle" is no evidence of surplus at all. The pool was emptied and
    // refaulted continuously — the frontier went from 109,605 pages back to
    // 194,068 and madvise traffic to 19 GB with 91% of it faulted straight
    // back, and no release FRACTION could fix it: 0.9^n is under 1% within 44
    // cycles, an effective horizon three orders of magnitude too short.
    //
    // So hold the rotation until at least one POOL'S WORTH of allocation has
    // gone by. Then a page reaching `aged` has sat through enough demand to
    // have been taken if anyone wanted it, which is the honest test — and it
    // self-calibrates off the pool's own size exactly as the surplus
    // measurement does, on the same allocation clock the rest of the GC uses.
    static size_t rotate_at = 0;
    size_t ever = atomic_load_explicit(&pages_ever, memory_order_relaxed);
    if (ever < rotate_at)
        return;

    // Pass 1: how much surplus is there? Read-only, so the fraction is decided
    // against the whole population rather than per pool.
    unsigned slots = pool_count();
    size_t surplus = 0;
    for (unsigned i = 0; i < slots; ++i) {
        page_pool_t *p = &pool_slots[i];
        pool_lock(p);
        surplus += p->aged.count;
        pool_unlock(p);
    }
    // Next rotation once a further pool's worth of allocation has passed. The
    // floor keeps a tiny or empty pool from rotating every call and turning
    // back into the per-cycle clock this replaced.
    size_t horizon = surplus > 256 ? surplus : 256;
    rotate_at = ever + horizon;

    size_t quota = surplus * pool_release_pct / 100;
    atomic_fetch_add_explicit(&pool_retained, surplus - quota, memory_order_relaxed);

    // Pass 2: drain `aged` up to the quota, then rotate every pool. What the
    // quota leaves behind stays in `aged` — still surplus, still first in line
    // to be reused, and released next cycle if demand still does not want it.
    size_t drained = 0, released = 0, lost_total = 0;
    for (unsigned i = 0; i < slots; ++i) {
        page_pool_t *p = &pool_slots[i];
        while (drained < quota) {
            size_t n = 0;
            pool_lock(p);
            while (n < BATCH && drained + n < quota
                   && pool_pop_locked(p, &p->aged, &batch[n]))
                n++;
            pool_unlock(p);
            if (n == 0)
                break;
            size_t rel = 0, lost = 0;
            pool_release_batch(batch, n, &rel, &lost);
            // Every entry the batch took out of the pool is accounted for.
            assert(rel + lost == n);
            drained  += n;
            released += rel;
            lost_total += lost;
        }
        // Rotate: this prune's frees become next cycle's surplus candidates.
        pool_lock(p);
        if (p->aged.top == NULL) {
            p->aged = p->fresh;
        } else {
            // Splice `fresh` under `aged` so the older entries stay on top and
            // are consumed (and judged) first.
            pool_chunk_t *c = p->aged.top;
            while (c->prev != NULL) c = c->prev;
            c->prev = p->fresh.top;
            p->aged.count += p->fresh.count;
        }
        p->fresh.top = NULL;
        p->fresh.count = 0;
        pool_unlock(p);
    }
    atomic_fetch_add_explicit(&pool_released, released, memory_order_relaxed);
    // POST-CONDITION: everything drained was either handed back to the OS or is
    // demonstrably in use again. This is the guarantee that a per-call page
    // budget would have destroyed — with one, "scheduled" and "released" differ
    // by an unknown amount and nothing can be asserted about either.
    assert(drained == released + lost_total);
    (void)lost_total;
}

EXPORT void memory_pool_release_stats(size_t* released, size_t* retained, size_t* lost,
                                      unsigned* pct) {
    *released = atomic_load_explicit(&pool_released, memory_order_relaxed);
    *retained = atomic_load_explicit(&pool_retained, memory_order_relaxed);
    *lost     = atomic_load_explicit(&pool_lost,     memory_order_relaxed);
    *pct      = pool_release_pct;
}

EXPORT void memory_pool_stats(size_t* hits, size_t* steals, size_t* stale,
                              size_t* misses, size_t* warm_at_miss) {
    *hits     = atomic_load_explicit(&pool_hits,       memory_order_relaxed);
    *steals   = atomic_load_explicit(&pool_steals,     memory_order_relaxed);
    *stale    = atomic_load_explicit(&pool_stale,      memory_order_relaxed);
    *misses       = atomic_load_explicit(&scan_miss,      memory_order_relaxed);
    *warm_at_miss = atomic_load_explicit(&scan_miss_warm, memory_order_relaxed);
}


// Pages handed out by memory_pages_alloc have UNDEFINED contents — stale data
// from their previous life (the page-claim memset that used to live here
// streamed whole runs through the cache long before their lines were needed).
// The consumer owns zeroing: the GC zeroes the page header at gc_page_alloc
// and each object's slots at the point of allocation, where the zero-writes
// land in L1 right under the field writes that follow. That zeroing is
// unconditional — never inherited from the kernel's zero-fill promise for
// virgin or madvised pages, so a future switch to MADV_FREE (whose pages keep
// their old contents until reclaim) cannot resurrect stale data.
// Every page below the watermark is in the singles_warm population from the
// moment the watermark exposes it (see the bump site, which increments) until
// someone claims it — so the decrement here is unconditional on band, with no
// need to know whether this claim came from reuse or from a fresh bump. An
// earlier attempt to distinguish the two with a `was_free` flag still missed
// the race where a concurrent scanner claims a page the bumping thread has
// just published.
static void* claimed_run(size_t idx, size_t page_count, bool was_free) {
    (void)was_free;
    atomic_fetch_add_explicit(&alloc_count, page_count, memory_order_relaxed);
    atomic_fetch_add_explicit(&pages_ever, page_count, memory_order_relaxed);
    size_t watermark = atomic_load_explicit(&upper_watermark, memory_order_relaxed);
    for (size_t j = 0; j < page_count; ++j) {
        if (atomic_exchange_explicit(&pages_cold[idx + j], 0, memory_order_relaxed)) {
            atomic_fetch_sub_explicit(&cold_count, 1, memory_order_relaxed);
            atomic_fetch_add_explicit(&scavenge_reclaimed, 1, memory_order_relaxed);
            if (page_count > 1)
                atomic_fetch_add_explicit(&scavenge_reclaimed_runs, 1, memory_order_relaxed);
        } else if (idx + j < watermark) {
            // Warm free page inside the singles band, now live (see singles_warm).
            atomic_fetch_sub_explicit(&singles_warm, 1, memory_order_relaxed);
        }
    }
    return pages_heap + idx * GC_PAGE_SIZE;
}

// The public entry: consult the per-thread pool (own, then steal) before doing
// any scanning at all. Only when no thread holds a claimable page does the
// bounded scan — and, failing that, a watermark bump — get to run.
EXPORT void* memory_pages_alloc(size_t page_count) {
    assert(page_count > 0);

    // pthread_once' own fast path is a single relaxed load; an outer
    // pages_heap-NULL check would race with the non-atomic write inside init().
    pthread_once(&pages_once, init);

    if (page_count == 1) {
        void* pooled = pool_take();
        if (pooled != NULL)
            return pooled;
    }
    return memory_pages_alloc_raw(page_count);
}

static void* memory_pages_alloc_raw(size_t page_count) {
    pthread_once(&pages_once, init);

    // New scavenge epoch: reset both cursors (see epoch_seen). The first
    // allocation of the epoch pays one long scan over the dense prefix;
    // everything after continues next-fit from the frontier it found.
    uint8_t epoch = scavenge_epoch_now();
    if (UNLIKELY(epoch != epoch_seen)) {
        epoch_seen = epoch;
        alloc_cursor = 0;
    }

    // Two-ended layout: SINGLES live in [0, upper_watermark) growing up,
    // RUNS live in [run_floor, total_page_count) growing down. Fresh pages
    // for each population come from its own end of the virgin middle, so the
    // populations never interleave and the runs band keeps its windows.
    if (page_count == 1) {
        while (true) {
            // Phase 1: reuse a free page within the singles region.
            size_t snapshot = atomic_load_explicit(&upper_watermark, memory_order_relaxed);
            size_t idx = scan_within(snapshot, 1, MAX_SCAN_PROBES, false);
            if (idx != SIZE_MAX) {
                return claimed_run(idx, 1, true);
            }

            // Phase 2: extend the singles region upward by one page. The
            // CAS-loop never advances into the runs band even under
            // concurrent bumps.
            //
            // The bounded scan found nothing. Was that honest? A warm free
            // page going spare means it stopped looking too soon. Counted
            // HERE rather than after the watermark CAS below, because the
            // waste is the same whether the miss ends in a bump or in the
            // unbounded whole-map rescan that follows once the two bands have
            // met — and it was that second case which made a watermark-delta
            // assertion read zero with the defect fully present.
            // Accumulate the POPULATION, not a yes/no. "Was any warm page
            // going spare" is nearly always true — a handful of strays makes
            // it read 100% — whereas the mean says how much was abandoned:
            // a mean of one or two is noise, a mean in the thousands is the
            // allocator walking away from megabytes.
            atomic_fetch_add_explicit(&scan_miss, 1, memory_order_relaxed);
            intptr_t warm = atomic_load_explicit(&singles_warm, memory_order_relaxed);
            atomic_fetch_add_explicit(&scan_miss_warm, warm > 0 ? (size_t)warm : 0,
                                      memory_order_relaxed);

            size_t cur = snapshot;
            while (true) {
                if (cur >= atomic_load_explicit(&run_floor, memory_order_relaxed)) {
                    // The regions have met. The bounded Phase-1 scan may have
                    // missed a usable hole; scan the WHOLE map (both bands)
                    // unbounded before declaring OOM.
                    size_t last = scan_within(total_page_count, 1, SIZE_MAX, true);
                    if (last != SIZE_MAX) {
                        return claimed_run(last, 1, true);
                    }
                    abort_on_out_of_memory();
                }
                if (atomic_compare_exchange_weak_explicit(
                        &upper_watermark, &cur, cur + 1,
                        memory_order_acq_rel, memory_order_relaxed)) {
                    // The page at `cur` is now inside the band and free, so it
                    // joins the warm population — whether this thread goes on
                    // to claim it or a concurrent scanner beats us to it. Both
                    // outcomes decrement exactly once.
                    atomic_fetch_add_explicit(&singles_warm, 1, memory_order_relaxed);
                    break;
                }
            }

            if (try_claim_run(cur, 1)) {
                // Deliberately do not move alloc_cursor here. scan_within
                // parked it just past where it gave up; preserving that lets
                // the next allocation resume the walk instead of redoing the
                // same fruitless probes from the bump location.
                return claimed_run(cur, 1, false);   // virgin: just exposed by the bump
            }
            // A concurrent scanner that observed our new watermark snuck in
            // and claimed the freshly exposed page first. The advance is not
            // wasted — loop and re-enter Phase 1 against the larger region.
        }
    }

    while (true) {
        // Phase 1: reuse a free window within the runs band.
        size_t floor = atomic_load_explicit(&run_floor, memory_order_relaxed);
        size_t idx = scan_runs_topdown(floor, page_count, MAX_SCAN_PROBES);
        if (idx != SIZE_MAX) {
            return claimed_run(idx, page_count, true);
        }

        // Phase 2: extend the runs band downward. Overflow-safe: check the
        // room below the floor before subtracting, and never cross the
        // singles watermark even under concurrent bumps from either end.
        size_t cur = floor;
        size_t begin;
        while (true) {
            size_t wm = atomic_load_explicit(&upper_watermark, memory_order_relaxed);
            if (cur < page_count || cur - page_count < wm) {
                // The regions have met (or the request exceeds the heap).
                // Last-ditch unbounded scan over the WHOLE map — a window may
                // straddle what the banded scans never look at.
                size_t last = scan_within(total_page_count, page_count, SIZE_MAX, true);
                if (last != SIZE_MAX) {
                    return claimed_run(last, page_count, true);
                }
                abort_on_out_of_memory();
            }
            begin = cur - page_count;
            if (atomic_compare_exchange_weak_explicit(
                    &run_floor, &cur, begin,
                    memory_order_acq_rel, memory_order_relaxed))
                break;
        }

        if (try_claim_run(begin, page_count)) {
            return claimed_run(begin, page_count, false);  // virgin runs-band pages
        }
        // A concurrent top-down scanner observed the lowered floor and took
        // the freshly exposed window first. The advance is not wasted — loop
        // and re-enter Phase 1 against the larger band.
    }
}

// The public entry: release the pages, then remember a single page in this
// thread's pool so the next single-page allocation finds it without scanning.
// The marker is FREE either way — pooling changes who looks first, never who
// may claim (see the pool header).
EXPORT void memory_pages_free(void* ptr, size_t page_count) {
    memory_pages_free_raw(ptr, page_count);
    if (page_count == 1)
        pool_give(ptr);
}

static void memory_pages_free_raw(void* ptr, size_t page_count) {
    assert(page_count > 0);
    assert(memory_pages_is_alloc_head(ptr));
    assert(((uintptr_t)ptr & (GC_PAGE_SIZE-1)) == 0);

    ptrdiff_t offset = ((char*)ptr - pages_heap) / GC_PAGE_SIZE;
    // The run must lie inside one of the two active bands (or have been
    // claimed by the whole-map last-ditch scan, which the total bound
    // covers).
    assert((size_t)(offset + page_count) <= total_page_count);

    // Caller claimed `page_count` pages. The page immediately following the
    // run must be either HEAD (next allocation), FREE, or past the heap end.
    // Anything else means the caller has truncated a multi-page allocation
    // and would leave dangling BODY markers no scanner could ever reclaim.
    if ((size_t)(offset + page_count) < total_page_count) {
        uint8_t after = atomic_load_explicit(&pages_info[offset + page_count], memory_order_relaxed);
        assert(after == PAGE_MARKER_HEAD || after == PAGE_MARKER_FREE);
        (void)after;   // assert-only
    }

    // Count backwards so that head is the last thing released
    for (ptrdiff_t index = (ptrdiff_t)page_count; --index >= 0; ) {
        uint8_t expected = (index == 0) ? PAGE_MARKER_HEAD : PAGE_MARKER_BODY;
        assert(atomic_load_explicit(&pages_info[offset + index], memory_order_relaxed) == expected);
        (void)expected;   // assert-only

        // No madvise here: freeing is hot-path. Returning memory to the OS
        // is the SCAVENGER's job (memory_scavenge below), which runs on the
        // GC's cycle clock and returns only pages the churn will not
        // immediately want back — measured by the free-age stamp below
        // (relaxed is enough: the scavenger's acquire CAS on the marker
        // orders its read after this store).
        atomic_store_explicit(&pages_free_epoch[offset + index],
            scavenge_epoch_now(), memory_order_relaxed);
        // A just-released page is warm by construction (see singles_warm).
        if ((size_t)(offset + index) < atomic_load_explicit(&upper_watermark, memory_order_relaxed))
            atomic_fetch_add_explicit(&singles_warm, 1, memory_order_relaxed);
        atomic_store_explicit(&pages_info[offset + index], PAGE_MARKER_FREE, memory_order_release);
    }

    atomic_fetch_sub_explicit(&alloc_count, page_count, memory_order_relaxed);
}

EXPORT bool memory_pages_is_alloc_head(void* ptr) {
    // Allocations live in both bands, so the bound is the whole map; virgin
    // middle pages read PAGE_MARKER_FREE (pages_info is zero-filled) and are
    // rejected by the marker check alone.
    ptrdiff_t offset = ((char*)ptr - pages_heap) / GC_PAGE_SIZE;
    return offset >= 0
        && (size_t)offset < total_page_count
        && atomic_load_explicit(&pages_info[offset], memory_order_relaxed) == PAGE_MARKER_HEAD;
}

// Resolve any address INSIDE an allocation — head page or a run's body
// pages — to the allocation's head page, or NULL when the address is not
// within a live allocation. Serves the conservative root scan's interior-
// pointer resolution. Tolerant of concurrent transitions: hitting FREE (a
// page being drained or re-initialised under us) rejects the candidate,
// which is always correct — live pages are never freed.
EXPORT void* memory_pages_alloc_head_of(void* ptr) {
    ptrdiff_t offset = ((char*)ptr - pages_heap) / GC_PAGE_SIZE;
    if (offset < 0 || (size_t)offset >= total_page_count)
        return NULL;
    for (;;) {
        uint8_t m = atomic_load_explicit(&pages_info[offset], memory_order_relaxed);
        if (m == PAGE_MARKER_HEAD) return pages_heap + (size_t)offset * GC_PAGE_SIZE;
        if (m != PAGE_MARKER_BODY || offset == 0) return NULL;
        offset--;
    }
}

// Hand the claimed run [lo, end) back to the OS and release it. Cold bit and
// counter go BEFORE the FREE release, page by page: once a page is FREE an
// allocator may take it at any instant, and claimed_run's exchange-and-
// decrement must always find the bit and the count already in place.
//
// Spans shorter than SCAVENGE_MIN_SPAN are NOT returned (see the knob
// comment): they are released warm, with their age stamps refreshed so the
// walk leaves them alone for another full age window.
static void scavenge_release(size_t lo, size_t end) {
    if (end == lo)
        return;
    // Every page in the span is HEAD — claimed by the walk below. That hold
    // is also what makes the whole-span madvise safe before any cold bit is
    // written: no allocator can touch a HEAD page mid-syscall.
    for (size_t k = lo; k < end; ++k) {
        assert(atomic_load_explicit(&pages_info[k], memory_order_relaxed) == PAGE_MARKER_HEAD);
    }
    size_t watermark = atomic_load_explicit(&upper_watermark, memory_order_relaxed);
    if (end - lo < SCAVENGE_MIN_SPAN) {
        uint8_t now = scavenge_epoch_now();
        for (size_t k = lo; k < end; ++k) {
            atomic_store_explicit(&pages_free_epoch[k], now, memory_order_relaxed);
            // Released still warm, so it re-joins the singles_warm population
            // that the claim took it out of. BEFORE the FREE store, for the
            // reason in this function's header: the instant the marker reads
            // FREE another thread may claim the page, and claimed_run's
            // decrement must never run ahead of this increment.
            if (k < watermark)
                atomic_fetch_add_explicit(&singles_warm, 1, memory_order_relaxed);
            atomic_store_explicit(&pages_info[k], PAGE_MARKER_FREE, memory_order_release);
            // NOT re-pooled. An earlier version pushed these back into a pool
            // so the scavenger could not strip warm pages out of it. That was
            // a stopgap from before the pool released anything itself, and it
            // manufactures DUPLICATE entries without bound: the same page is
            // re-pooled every cycle it survives, and each copy is popped and
            // discarded later. Measured at 62.8M stale drops against 28.1M
            // allocations on one self-compile. The page stays FREE and warm
            // and the fallback scan can still find it; the pool's own release
            // is what governs the population now.
        }
        return;
    }
    madvise(pages_heap + lo * GC_PAGE_SIZE, (end - lo) * GC_PAGE_SIZE, MADV_DONTNEED);
    for (size_t k = lo; k < end; ++k) {
        atomic_store_explicit(&pages_cold[k], 1, memory_order_relaxed);
        atomic_fetch_add_explicit(&cold_count, 1, memory_order_relaxed);
        atomic_store_explicit(&pages_info[k], PAGE_MARKER_FREE, memory_order_release);
    }
    atomic_fetch_add_explicit(&scavenge_returned, end - lo, memory_order_relaxed);
}

// Return excess free pages to the OS with madvise(MADV_DONTNEED), keeping at
// least `retain` WARM (never-advised) free pages as allocation slack so the
// steady-state churn never touches the kernel. Walks the active region
// top-down, resuming where the previous call stopped: with singles packing
// low and runs packing high, the highest free pages are the coldest —
// typically the corpse of a large transient. At most `max_pages` pages are
// returned per call, bounding the madvise work on the GC's clock.
//
// Ownership dance: each candidate is claimed with the allocator's own CAS
// (FREE→HEAD), advised, marked cold, then released back to FREE — a page is
// never advised while claimable, so the kernel cannot zero-fill under data
// an allocator has just handed out. Adjacent claims merge into one madvise.
//
// Must be called under the GC's fsa_lock (it is the only caller): the
// transient HEAD marker would otherwise be visible to the conservative
// scanner's memory_pages_is_alloc_head probes while the page still holds a
// stale magic word from its former life. The resume cursor relies on the
// same single-caller contract.
EXPORT void memory_scavenge(size_t retain, size_t max_pages) {
    if (pages_info == NULL)
        return;
    size_t watermark = atomic_load_explicit(&upper_watermark, memory_order_relaxed);
    size_t floor     = atomic_load_explicit(&run_floor, memory_order_relaxed);
    // Pages ever part of an allocation live in the two bands; the virgin
    // middle is skipped by the walk below.
    size_t extent = watermark + (total_page_count - floor);
    if (extent == 0)
        return;

    // The age clock is allocation volume, not this call's cadence: the GC
    // invokes us once per cycle, but eligibility below compares stamps
    // against the epoch derived from cumulative pages claimed.
    uint8_t now = scavenge_epoch_now();

    size_t cold = atomic_load_explicit(&cold_count, memory_order_relaxed);
    size_t used = atomic_load_explicit(&alloc_count, memory_order_relaxed);

    // Demand-peak retain: never return below the recent HIGH-WATER of used
    // pages. Bursty demand (findstr's variable-size file buffers) re-fits
    // inside the retained envelope instead of bouncing through the kernel —
    // no per-page idleness clock can see that a span idle through many
    // epochs is still part of a recurring peak. The peak decays by 1/64 per
    // call (one call per GC cycle), so only a SUSTAINED drop in footprint
    // releases pages; a dead transient still goes back, ~a hundred cycles
    // later. Single caller under fsa_lock, like scavenge_cursor.
    static size_t demand_peak = 0;
    demand_peak -= demand_peak / 64;
    if (used > demand_peak)
        demand_peak = used;
    size_t hold = demand_peak - used;
    if (retain < hold)
        retain = hold;

    // Quota: bounded by the per-call budget and by the warm slack above the
    // retain target. Sampled once — allocations racing past us only shrink
    // the real slack, and the next call corrects either way.
    size_t warm_free = sat_sub(extent, used + cold);
    if (warm_free <= retain + SCAVENGE_HYSTERESIS)
        return;
    size_t quota = warm_free - retain;
    if (quota > max_pages)
        quota = max_pages;

    // Resume where the previous call stopped. Both 0 (bottom reached) and
    // anything beyond the heap end mean "start a fresh pass from the top of
    // the runs band"; a cursor stranded in the virgin middle (the floor
    // moved) snaps down to the singles band inside the loop.
    size_t i = scavenge_cursor;
    if (i == 0 || i > total_page_count)
        i = total_page_count;

    size_t scanned = 0;            // bounds the walk to one full lap
    size_t run_lo = 0, run_end = 0; // pending claimed run, growing downward
    while (quota > 0 && scanned < extent) {
        if (i == 0) {
            scavenge_release(run_lo, run_end);
            run_lo = run_end = 0;
            i = total_page_count;
            continue;   // wrap is free, like the allocation scans
        }
        if (i <= floor && i > watermark) {
            // Crossing from the runs band into the virgin middle: flush the
            // pending span (spans never straddle the gap) and hop to the top
            // of the singles band. Free move, like the wrap.
            scavenge_release(run_lo, run_end);
            run_lo = run_end = 0;
            i = watermark;
            continue;
        }
        size_t cand = --i;
        ++scanned;

        // Eligible = warm, FREE, and free-aged (the churn has demonstrably
        // not wanted it back for SCAVENGE_FREE_AGE young-heap turnovers).
        bool claimed = false;
        if (!atomic_load_explicit(&pages_cold[cand], memory_order_relaxed)
                && (uint8_t)(now - atomic_load_explicit(&pages_free_epoch[cand], memory_order_relaxed))
                    >= SCAVENGE_FREE_AGE) {
            uint8_t expected = PAGE_MARKER_FREE;
            claimed = atomic_compare_exchange_strong_explicit(
                &pages_info[cand], &expected, PAGE_MARKER_HEAD,
                memory_order_acq_rel, memory_order_relaxed);
            // Eligibility above required it warm, so a won claim takes a page
            // out of the singles_warm population; scavenge_release puts it
            // back if the span turns out too short to return.
            if (claimed && cand < watermark)
                atomic_fetch_sub_explicit(&singles_warm, 1, memory_order_relaxed);
        }
        if (claimed) {
            if (run_end != 0 && cand + 1 == run_lo) {
                run_lo = cand;
            } else {
                scavenge_release(run_lo, run_end);
                run_lo = cand;
                run_end = cand + 1;
            }
            --quota;
        } else if (run_end != 0) {
            scavenge_release(run_lo, run_end);
            run_lo = run_end = 0;
        }
    }
    scavenge_release(run_lo, run_end);
    scavenge_cursor = i;
}

EXPORT void memory_scavenge_stats(size_t* returned, size_t* reclaimed, size_t* cold_now,
                                  size_t* reclaimed_runs) {
    *returned  = atomic_load_explicit(&scavenge_returned,  memory_order_relaxed);
    *reclaimed = atomic_load_explicit(&scavenge_reclaimed, memory_order_relaxed);
    *cold_now  = atomic_load_explicit(&cold_count,         memory_order_relaxed);
    *reclaimed_runs = atomic_load_explicit(&scavenge_reclaimed_runs, memory_order_relaxed);
}

EXPORT size_t memory_count() {
    return alloc_count;
}

EXPORT size_t memory_watermark() {
    return atomic_load_explicit(&upper_watermark, memory_order_relaxed);
}

// Bottom of the runs band (multi-page allocations grow DOWN from the top of
// the map). Pages ever part of an allocation live in [0, memory_watermark())
// and [memory_run_floor(), memory_total_pages()).
EXPORT size_t memory_run_floor() {
    return atomic_load_explicit(&run_floor, memory_order_relaxed);
}

// Capacity of the whole managed heap in pages (YAFL_HEAP_SIZE / GC_PAGE_SIZE).
// Zero until the first allocation initialises the heap.
EXPORT size_t memory_total_pages() {
    return total_page_count;
}


