
#define OBJECT_HEADER_EXCLUSIONS

#include "yafl.h"
#include "gc_internal.h"
#include "prof.h"
#include "heapprof.h"
#include <malloc.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include <time.h>


#define COMPACT_THRESHOLD_PERCENT   33
#define REPROCESS_PAGE_COUNT        16

// ═══ COLLECTOR PROTOCOL — the one-page map ═══════════════════════════════════
//
// STAGES  (enum gc_stage, gc_internal.h; `stage` is the atomic word):
//
//   IDLE -> START -> SCAN_ROOTS -> MARK_SWEEP -> PRUNE -> IDLE ...
//
//   There are NO dedicated GC threads: every allocating worker drives the
//   machine through gc_fsa(), paced by its own allocation (see pacing below).
//   START and SCAN_ROOTS are EXCLUSIVE — one executor at a time under
//   fsa_lock. MARK_SWEEP and PRUNE are PARALLEL — every caller becomes an
//   executor, takes no lock, and claims work page-by-page.
//
// OWNERSHIP  Page claims are the unit of parallelism: an executor pops a page
//   from pages_to_scan / pages_to_prune (under gc_pool_lock) and then owns it
//   outright — a claimed page is UNLINKED and invisible to everyone else, so
//   per-page state (seen/scanned bitmaps) needs no further synchronisation.
//   Concurrent requeues aimed at a claimed page park in
//   page->scanner.requeue_pending, consumed by the owner.
//
// LOCKS
//   fsa_lock      exclusive stages + all stage TRANSITIONS (CAS bool).
//   gc_pool_lock  page-list surgery ONLY (O(1) sections; every splice on
//                 pages_to_scan/prune/old during parallel stages goes under
//                 it — no exceptions, that rule has been paid for twice).
//   gc_in_fsa     thread-local re-entrancy guard: collector work that
//                 allocates (compaction refill) must not nest an executor.
//
// TRANSITIONS quiesce on gc_pages_in_flight == 0 — pages claimed but not yet
//   returned — NEVER on the executor count, which churns per paced step and
//   would starve the transition under sustained allocation. The last
//   executor whose step found no work re-verifies under fsa_lock and moves
//   the stage (gc_fsa_try_transition).
//
// PACING  Collection rate is proportional to allocation rate EXACTLY:
//   allocations advance gc_alloc_clock (pages); executors CAS-claim bounded
//   slices of the unclaimed backlog (gc_pace_credit). Aggregate claims can
//   never exceed aggregate allocation. The reserve gate in gc_page_alloc is
//   the backstop: a nearly-full heap stalls allocators into driving cycles
//   synchronously, and compaction's evacuation targets come from a reserve
//   ordinary allocation may not consume.
//
// MODULES  gc_stats.c (counters + [GC]/[GC TIME] reporting), gc_debug.c
//   (poison dangle check, YAFL_GC_HUNT census), mmap.c (page provider +
//   madvise scavenger), gc_internal.h (shared state + the pointer-window
//   walker). The allocation fast path is inline in yafl.h (generated code).
// ═════════════════════════════════════════════════════════════════════════════

// --- GC pacing --------------------------------------------------------------
//
// The collector runs CONTINUOUSLY: there is no idle dwell between cycles —
// PRUNE hands straight back to START on the next allocation. The rate of
// collection is linked directly to the rate of allocation, and the pacing is
// stated in PAGES, and nothing else: per page allocated,
//
//     scan  GC_PACE_SCAN_PAGES  (r) pages, and
//     prune GC_PACE_PRUNE_PAGES  (p) pages — INDEPENDENT of r: a lower scan
//     ratio stretches sweep completion and so grows the garbage backlog per
//     completed sweep, which is exactly when prune must NOT slow with it.
//
// The progress guarantee is STRUCTURAL, not feedback-driven: a cycle over S
// pages is scanned within S/r allocations — the world is scanned before the
// young set can grow by 1/r — and pruned within a further S/(16r). No
// emergency mode, no headroom feedback; the fixed ratios
// outrun allocation by construction, and every gc_fsa call costs a similar,
// predictable quantum (a couple of page scans, or a few dozen page prunes —
// roughly the same wall time each; [GC LAT] under YAFL_GC_STATS shows the
// distribution). The relocation-reserve gate in gc_page_alloc remains the
// backstop for a genuinely full heap.
//
// Safe points do NO collection work of their own; they only repay catch-up
// debt recorded when an allocation-driven step failed to win fsa_lock
// (lag_counter + GC_SAFE_POINT_CATCH_UP, one bounded step per safe point).
//
// YAFL_GC_STEP_PAGES overrides the scan ratio; YAFL_GC_PRUNE_PAGES overrides
// the prune ratio independently (default 64 = the old 16x-of-4 coupling's
// effective value): larger = more GC work per allocation = tighter heap,
// higher GC share of CPU.
#define GC_PACE_SCAN_PAGES  4     // pages scanned per page allocated — THE knob.
                                  // Peak heap ≈ live x (r+1)/(r-1): r=2 is 3x
                                  // live (measured), r=4 is 1.67x with most of
                                  // the GC-CPU win kept; tune via env per
                                  // deployment.
#define GC_PACE_PRUNE_PAGES 64    // pages pruned per page allocated (prune is
                                  // cheap per page); deliberately NOT derived
                                  // from the scan ratio — see pacing comment
#define GC_PACE_CREDIT_MAX  16    // max allocation-pages consumed per gc_fsa
                                  // call; a backlog (multi-page allocation,
                                  // credit accrued across the roots phase)
                                  // drains over a few calls instead of
                                  // spiking one
#define GC_PACE_LAG_MAX     4096  // cap on a thread's accumulated catch-up debt
static unsigned gc_step_base  = GC_PACE_SCAN_PAGES;
static unsigned gc_prune_base = GC_PACE_PRUNE_PAGES;

// Scavenger call-site knobs (the scavenger itself lives in mmap.c, with its
// own age/hysteresis tuning). The retain floor only smooths intra-cycle
// allocation — the free-age gate is what protects the churn's pages — so a
// small floor suffices and keeps small programs small. The budget bounds the
// madvise work done per cycle.
#define GC_SCAVENGE_RETAIN_FLOOR  256   // pages (4 MiB) of warm slack always kept
#define GC_SCAVENGE_BUDGET        1024  // max pages returned per cycle

// Cap on the refs_are_old re-walk backoff (see page_head.refs_backoff): a
// permanently blocked page costs one full page walk per cap+1 prunes instead
// of one per prune; an honestly blocked page graduates at most this many
// cycles late, during which it remains a force-marked dirty root (sound).
#define GC_REFS_BACKOFF_CAP       64

// --- Debug toggles (all off by default) --------------------------------------
//
// YAFL_GC_POISON: memset reclaimed objects to 0x42 at prune time, and verify
// during marking that no live object's pointer field references a poisoned
// one (aborting with the offending edge). Turns a latent use-after-free into
// a deterministic, clearly-reported failure. Costs a memset per reclaimed
// object plus a field walk per scanned object — debugging only.
//
// YAFL_GC_STATS: GC diagnostics to stderr — a sampled progress line every 512
// page allocations plus a [GC TIME] summary at exit.
//
// YAFL_GC_HUNT (with YAFL_GC_STATS): exit-time heap census and retention
// hunt — see the heap-hunt comment further down.
EXPORT bool gc_debug_manual_mode = false;
bool gc_poison_enabled = false;
bool gc_stats_enabled  = false;
// YAFL_GC_GEN=0 disables the generational machinery (default ON). Gated at a
// single point — page promotion — so with it off no page ever becomes old and
// the skip paths, dirty-old handling and major trigger are all inert.
static bool gc_gen_enabled    = true;
static void gc_read_config(void) {
    const char *e;
    if ((e = getenv("YAFL_GC_STEP_PAGES")) != NULL) {
        int base = atoi(e);
        if (base > 0) gc_step_base = (unsigned)base;
    }
    if ((e = getenv("YAFL_GC_PRUNE_PAGES")) != NULL) {
        int base = atoi(e);
        if (base > 0) gc_prune_base = (unsigned)base;
    }
    gc_poison_enabled = (e = getenv("YAFL_GC_POISON")) && e[0] && e[0] != '0';
    gc_stats_enabled  = getenv("YAFL_GC_STATS") != NULL;
    gc_gen_enabled    = !((e = getenv("YAFL_GC_GEN")) && e[0] == '0');
}


#ifndef NDEBUG
#define NOINLINE_DEBUG NOINLINE
#else
#define NOINLINE_DEBUG
#endif


EXPORT volatile bool gc_write_barrier_requested = false;



EXPORT void abort_on_vtable_lookup() {
    log_error_and_exit("Aborting due to vtable lookup issue", stderr);
}

EXPORT void abort_on_too_large_object() {
    log_error_and_exit("Aborting due to unsupported object size failure", stderr);
}

EXPORT void abort_on_heap_allocation_on_non_worker_thread() {
    log_error_and_exit("Aborting due to attempted allocation on uninitialised thread", stderr);
}

EXPORT void abort_on_array_bounds() {
    log_error_and_exit("Aborting due to array index out of bounds", stderr);
}




// The heap geometry (mask_bits_t, bitmap_t, slot_t, page_head_t, gc_page_t,
// SLOTS_PER_PAGE, MAX_OBJECT_SIZE, PAGE_MAGIC_NUMBER) lives in yafl.h — the
// allocation fast path is inlined into generated code and needs it there.
// These asserts cross-check the arithmetic stays true to GC_PAGE_SIZE.
static_assert(sizeof(gc_page_t) == GC_PAGE_SIZE, "Page size doesn't add up");
static_assert(sizeof(slot_t) == GC_SLOT_SIZE, "Slot size doesn't add up");

// list_element_t: gc_internal.h



static __attribute__((unused)) unsigned bitmap_count(const bitmap_t *bitmap) {
    unsigned count = 0;
    for (unsigned index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index)
        count += __builtin_popcountll(bitmap->a[index]);
    return count;
}

// bitmap_fetch_set / atomic_bitmap_fetch_set live in yafl.h (the inline
// allocation fast path uses them).

static void bitmap_reset_all(bitmap_t *bitmap) {
    memset(bitmap, 0, sizeof(bitmap_t));
}

static bool bitmap_test(const bitmap_t *bitmap, unsigned bit) {
    return (bitmap->a[bit / GC_MASK_SIZE] & (((mask_bits_t)1) << (bit % GC_MASK_SIZE))) != 0;
}

static bool bitmap_test_all(const bitmap_t *bitmap) {
    mask_bits_t result = 0;
    for (unsigned index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index)
        result |= bitmap->a[index];
    return result != 0;
}

static bool bitmap_or_test_reset_all(bitmap_t * __restrict target, bitmap_t * __restrict source) {
    mask_bits_t result = 0;
    for (unsigned index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index) {
        _Atomic(mask_bits_t) *src_ptr = (_Atomic(mask_bits_t)*)&source->a[index];
        mask_bits_t bits = atomic_exchange(src_ptr, 0);
        result |= (target->a[index] |= bits);
    }
    return result != 0;
}

// Like the two above, but reports whether the merge added bits the TARGET did
// not already have. This is the only condition safe to LOOP on: target bits
// are monotonic within an epoch (bounded by the page's 512 slots), so a
// merge-and-rescan fixpoint terminates unconditionally — where testing the
// target (always non-empty once anything merged) spins forever, and testing
// the source spins for as long as mutator barriers keep re-marking objects
// that are already live.
static bool bitmap_or_test_new_reset_all(bitmap_t * __restrict target, bitmap_t * __restrict source) {
    mask_bits_t result = 0;
    for (unsigned index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index) {
        _Atomic(mask_bits_t) *src_ptr = (_Atomic(mask_bits_t)*)&source->a[index];
        mask_bits_t bits = atomic_exchange(src_ptr, 0);
        result |= bits & ~target->a[index];
        target->a[index] |= bits;
    }
    return result != 0;
}

// Like bitmap_or_test_reset_all, but reports whether the SOURCE contributed any
// bits (i.e. new marks arrived), NOT whether the merged target is non-empty.
// Used by the post-scan drain to re-queue a page only when fresh marks actually
// landed during the scan — otherwise every non-empty page would be re-queued
// forever and the mark-sweep cycle could never drain.
static bool bitmap_or_test_source_reset_all(bitmap_t * __restrict target, bitmap_t * __restrict source) {
    mask_bits_t result = 0;
    for (unsigned index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index) {
        _Atomic(mask_bits_t) *src_ptr = (_Atomic(mask_bits_t)*)&source->a[index];
        mask_bits_t bits = atomic_exchange(src_ptr, 0);
        target->a[index] |= bits;
        result |= bits;
    }
    return result != 0;
}

static void list_unlink(list_element_t *node) {
    node->next->prev = node->prev;
    node->prev->next = node->next;
    // An unlinked node's own links are nulled: "not on any list" is now an
    // observable state — a page claimed by an executor — that concurrent
    // requeue requests must detect (see page_needs_scan) rather than splice
    // through stale pointers.
    node->next = NULL;
    node->prev = NULL;
}

static list_element_t *list_pop(list_element_t *root) {
    list_element_t *head = root->next;
    if (head == root) return NULL;
    list_unlink(head);
    return head;
}

static void list_link(list_element_t *root, list_element_t *node) {
    node->next = root;
    node->prev = root->prev;
    root->prev->next = node;
    root->prev = node;
}

static void list_move(list_element_t *target, list_element_t *source) {
    if (source->next != source) {
        source->next->prev = target->prev;
        target->prev->next = source->next;
        source->prev->next = target;
        target->prev = source->prev;
        source->prev = source;
        source->next = source;
    }
}

static bool list_empty(list_element_t *root) {
    return root == root->next;
}


static bool gc_fsa();


// gc_stage / thread_state enums: gc_internal.h



// The per-thread ALLOCATION state (safe_point_request + bump regions) is the
// public `gc_alloc_tl` thread-local from yafl.h — the inline fast path in
// generated code reads and writes it directly. The rest of the thread record
// stays private here; `alloc` points at the owning thread's gc_alloc_tl so
// the collector's remote accesses (root-scan region reset, safe-point
// requests) reach it through the `threads` chain.
EXPORT thread_local gc_alloc_tl_t gc_alloc_tl = {0};

thread_local struct gc_thread_info gc_thread_info;   // type: gc_internal.h

_Atomic(struct gc_thread_info*) threads = NULL;
_Atomic(enum gc_stage) stage = GC_STAGE_NOT_STARTED;

// ── Parallel-executor state (P1) ────────────────────────────────────────────
// MARK_SWEEP and PRUNE admit ANY number of workers stepping concurrently:
// each claims whole pages (page ownership serialises the per-page work), so
// contention is per page, never per object. Stage TRANSITIONS stay exclusive:
// the last executor out takes fsa_lock, re-verifies completion, and moves the
// stage. Cache-line alignment keeps each hot shared word off the others'
// lines (and off the read-mostly globals around them).
static alignas(CACHE_LINE_SIZE) _Atomic(int)  gc_stage_executors = 0;
// Pages currently CLAIMED by executors (popped, being processed). This — not
// the executor count — is the transition quiescence gate: executors enter and
// exit constantly under sustained allocation (every paced step), so waiting
// for executors==0 starves the transition indefinitely; waiting for zero
// in-flight PAGES only waits for real work to finish.
static alignas(CACHE_LINE_SIZE) _Atomic(int)  gc_pages_in_flight = 0;
alignas(CACHE_LINE_SIZE) _Atomic(bool) gc_pool_lock_word = false;

// gc_pool_lock/unlock: gc_internal.h
uint32_t                     epoch = 0; // Must never be 0, except now

// Bumped each time gc_fsa_prune drains pages_to_prune to empty (i.e., a full
// GC cycle has completed). Diagnostic only.
_Atomic(uint64_t)            gc_cycle_count = 0;

static _Atomic(gc_page_t*) reprocess_page_list[REPROCESS_PAGE_COUNT];
static atomic_size_t       reprocess_page_head;
static atomic_size_t       reprocess_page_tail;
static atomic_bool         reprocess_overflow_flag;

// Mark worklist: a GROWABLE LIFO stack of objects discovered on an
// ALREADY-PROCESSED page (a "back-edge" — a reference into a page the scanner
// has already finished). Such objects are scanned DIRECTLY instead of
// re-queueing and re-diffing their whole page.
//
// It is drained to EMPTY at the end of every page scan (see
// gc_fsa_mark_sweep): scanning a page pushes its back-edges, then the drain
// chases them — each scan can push more, so it eats the top of the stack
// while pushing back to it until nothing remains. A page popped from
// pages_to_scan is therefore FULLY resolved, back-edge closure included,
// before the next pop. That keeps the structural pacing exact: the cycle does
// one page-pop per live page, with no overflow requeue competing for the
// "scan N pages per allocation" budget (the old fixed array fell back to
// re-queueing the whole page when full — extra page-pops the budget never
// accounted for).
//
// LIFO, not FIFO: depth-first keeps allocation-ordered chains streaming under
// the hardware prefetcher (a FIFO worklist measured ~30% slower). Chunked so
// it grows without bound; each chunk is a single page from the runtime's own
// page allocator (NOT libc malloc — the runtime manages memory through
// memory_pages_alloc throughout), holding undefined contents we overwrite
// before reading. Emptied chunks return to a freelist, so steady state —
// where each page's back-closure fits one chunk — never allocates; the reset
// path trims the freelist so a one-off closure spike is not retained for the
// program's life. PER-WORKER (thread_local): each stepping worker drains its
// own stack to empty before its step ends, so no entries ever cross threads —
// the precondition for concurrent mark executors. A worker's freelist keeps at
// most MARK_FREELIST_KEEP pages cached (bounded by worker count); the
// mutator-side barrier keeps its own reprocess ring.
enum { MARK_CHUNK_CAP = (GC_PAGE_SIZE - 2 * sizeof(void*)) / sizeof(object_t*) };
enum { MARK_FREELIST_KEEP = 4 };        // chunks cached across cycles, per worker
typedef struct mark_chunk {
    struct mark_chunk *prev;            // chunk below this one on the stack
    size_t             count;           // entries in use
    object_t          *slots[MARK_CHUNK_CAP];
} mark_chunk_t;
static thread_local mark_chunk_t *mark_top  = NULL;  // top chunk, NULL when the stack is empty
static thread_local mark_chunk_t *mark_free = NULL;  // recycled-chunk freelist (linked via ->prev)
static thread_local size_t        mark_free_count = 0;
thread_local size_t               mark_worklist_count = 0;  // diagnostic depth (this worker; for [GC] stats)

static void mark_worklist_push(object_t *o) {
    if (mark_top == NULL || mark_top->count == MARK_CHUNK_CAP) {
        mark_chunk_t *c = mark_free;
        if (c) {
            mark_free = c->prev;
            mark_free_count--;
        } else {
            c = memory_pages_alloc(1);   // one page; aborts on true OOM
        }
        c->prev = mark_top;
        c->count = 0;
        mark_top = c;
    }
    mark_top->slots[mark_top->count++] = o;
    mark_worklist_count++;
}

static object_t *mark_worklist_pop(void) {
    if (mark_top == NULL) return NULL;
    object_t *o = mark_top->slots[--mark_top->count];
    mark_worklist_count--;
    if (mark_top->count == 0) {          // recycle the emptied chunk
        mark_chunk_t *empty = mark_top;
        mark_top = empty->prev;
        empty->prev = mark_free;
        mark_free = empty;
        mark_free_count++;
    }
    return o;
}

// Splice any remaining chunks onto the freelist, then trim it to a small cap.
// The stack is already empty at every step boundary (drained per page), so the
// splice loop normally does nothing — it keeps the cycle-reset path total — and
// the trim returns a one-off spike's pages to the allocator instead of holding
// them forever.
static void mark_worklist_reset(void) {
    while (mark_top != NULL) {
        mark_chunk_t *c = mark_top;
        mark_top = c->prev;
        c->prev = mark_free;
        mark_free = c;
        mark_free_count++;
    }
    while (mark_free_count > MARK_FREELIST_KEEP) {
        mark_chunk_t *c = mark_free;
        mark_free = c->prev;
        mark_free_count--;
        memory_pages_free(c, 1);
    }
    mark_worklist_count = 0;
}


/**
 * Add separate bitmap for atomic marking during early root marking phase.
 * Wipe that bitmap when doing mark-sweep, ready for next iteration.
 */

// Each list head on its own cache line: they are touched under gc_pool_lock
// from every executor, and two adjacent 16-byte heads on one line measurably
// false-share (perf c2c: 5.8% of HITM traffic at T=12).
alignas(CACHE_LINE_SIZE) list_element_t pages_to_scan  = {&pages_to_scan, &pages_to_scan};
alignas(CACHE_LINE_SIZE) list_element_t pages_to_prune = {&pages_to_prune, &pages_to_prune};

// --- Generations (immutability-based) ----------------------------------------
//
// In a pure language an immutable object's referents are allocated before it,
// and pages promote by age, so an old immutable page can never reference a
// young object — there is no remembered set to keep. Promotion is VOLUME
// based: an immutable single page moves to `old_pages` once it has stayed
// stable (no deaths at any prune) across at least two dwell windows' worth
// of allocation — the young heap turning over twice. A cycle-count criterion
// is meaningless across cycle-length regimes: with short cycles it promoted
// mid-life churn wholesale (yspell accreted ~190 MiB of dirty pages whose
// garbage the force-mark then froze). Promoted pages leave the scan/prune
// rotation entirely, and every mark source skips them: minor cycles trace
// only young pages plus the (small) mutable set. Old garbage is reclaimed by
// MAJOR cycles, which pull `old_pages` back into the rotation and run an
// ordinary full trace; a major is triggered when the old generation has
// doubled since the last one (with a floor, so small programs never bother).
// Compacted pages never promote — their forwarders point at YOUNG copies,
// which the old-skip would lose.
#define GC_MAJOR_FLOOR   256   // pages: no majors until the old gen reaches this
alignas(CACHE_LINE_SIZE) list_element_t old_pages = {&old_pages, &old_pages};
_Atomic(uint64_t) gc_alloc_clock = 0; // cumulative pages ever allocated
static size_t gc_promote_volume = 0;  // pages of allocation a page must stay
                                      // stable across to promote: eight young
                                      // turnovers, set at each prune's end.
_Atomic(size_t) gc_old_page_count   = 0;
_Atomic(size_t) gc_dirty_old_count  = 0;   // diagnostic: dirty-old pages this cycle
static size_t gc_old_baseline   = 0;     // old-gen size right after the last major
static bool   gc_major_cycle    = false; // current cycle includes the old generation
static bool   gc_major_request  = false; // debug: force the next cycle major


// --- Continuous collection ---------------------------------------------------
//
// There is NO dwell between cycles: the FSA chains PRUNE -> IDLE -> START on
// the very next allocation-driven step, so the system is in a permanent GC
// cycle. RSS therefore tracks the live set, not a policy multiplier. The
// throttle is the fixed pages-per-allocation ratio (see the pacing comment
// at the top of the file); near full, the reserve gate in gc_page_alloc
// stalls allocators and drives cycles synchronously.
// One companion mechanism in gc_page_alloc covers the only true
// deadlock: the relocation reserve (ordinary allocation may not consume the
// last pages — compaction needs them as evacuation targets, else a
// nearly-full heap wedges: pages cannot be freed because freeing them needs
// pages).
//
// "Survivors" counts pages that came through PRUNE alive; the byte-honest
// young-slot count feeds the generational promotion volume below (pages
// allocated during the cycle are birth-protected, never enter the prune
// list, and so are deliberately excluded from both).
extern size_t memory_total_pages(void);
extern size_t memory_count(void);
static _Atomic(size_t) gc_cycle_survivors  = 0;   // pages surviving PRUNE this cycle
static _Atomic(size_t) gc_cycle_survivor_slots = 0; // live SLOTS on young survivors (byte-honest)

// Pacing is stated in PAGES, and nothing else: per page allocated, the
// collector scans GC_PACE_SCAN_PAGES pages and prunes GC_PACE_PRUNE_PAGES
// pages. The progress guarantee is structural, not feedback-driven — with a
// scan ratio of 2, a cycle over S pages completes within S/2 allocations
// (the world is scanned before the young set grows 50%), and pruning lands
// within a further ~3%. Every gc_fsa call costs a similar, predictable
// quantum.
//
// The budget is drawn from the allocation CLOCK, so the books balance
// exactly: a multi-page allocation deposits its full page count, a call
// that loses fsa_lock leaves its delta for the next holder, and stages that
// do no page work (START, SCAN_ROOTS) let credit accrue. Consumption is
// capped per call so an accrued backlog drains over a few calls instead of
// spiking one, and floored at 1 so a call always progresses (manual-mode
// stepped tests allocate nothing). The floor can over-deliver work; it
// never runs the accounting ahead of the clock.
// The pacing CLAIM POOL: allocations advance gc_alloc_clock; every stepping
// executor atomically claims a bounded slice of the un-claimed backlog. The
// aggregate claimed work can never exceed the aggregate allocation, so the
// "collection rate is proportional to allocation rate" invariant holds
// EXACTLY under any number of concurrent executors — and now scales with
// them. The floor of 1 keeps every step productive (its aggregate excess is
// one page per step, the same property the serial pacing had).
static alignas(CACHE_LINE_SIZE) _Atomic(uint64_t) gc_pace_claimed = 0;
static unsigned gc_pace_credit(void) {
    uint64_t now = atomic_load_explicit(&gc_alloc_clock, memory_order_relaxed);
    uint64_t claimed = atomic_load_explicit(&gc_pace_claimed, memory_order_relaxed);
    for (;;) {
        uint64_t backlog = now > claimed ? now - claimed : 0;
        unsigned take = backlog > GC_PACE_CREDIT_MAX ? GC_PACE_CREDIT_MAX : (unsigned)backlog;
        if (take == 0)
            return 1;
        if (atomic_compare_exchange_weak_explicit(&gc_pace_claimed, &claimed, claimed + take,
                                                  memory_order_relaxed, memory_order_relaxed))
            return take;
    }
}


// GC stats counters + [GC]/[GC TIME] reporting: gc_internal.h + gc_stats.c
// Heap hunt (YAFL_GC_HUNT): gc_debug.c



// Live slot count for a single page, from the objects/seen bitmaps alone
// (object extent = start bit to next start bit), never vtables. Used by the
// stats survey AND by the dwell threshold, which wants live BYTES: a page
// granularity count over-states the live set wherever live and dead objects
// interleave on the same pages (e.g. a kept list interleaved with a dropped
// intermediate runs every page at ~50%).
static unsigned gc_page_live_slots(gc_page_t *page) {
    unsigned live_slots = 0, prev_slot = 0;
    bool prev_live = false;
    for (unsigned index = 0; index < sizeof(bitmap_t) / sizeof(mask_bits_t); ++index) {
        mask_bits_t starts = page->head.objects.a[index];
        // One word load instead of a bitmap_test memory access per object:
        // a start is live iff its bit is also set in seen.
        mask_bits_t lives  = starts & page->head.scanner.seen.a[index];
        unsigned    offset = index * GC_MASK_SIZE;
        while (starts) {
            unsigned bit  = (unsigned)__builtin_ctzll(starts);
            starts &= starts - 1;
            unsigned slot = offset + bit;
            if (prev_live) live_slots += slot - prev_slot;
            prev_slot = slot;
            prev_live = (lives >> bit) & 1;
        }
    }
    if (prev_live) live_slots += SLOTS_PER_PAGE - prev_slot;
    return live_slots;
}

static void gc_occupancy_account(gc_page_t *page) {
    if (page->head.pages > 1) {
        gc_occ_large += page->head.pages;
        return;
    }
    unsigned live_slots = gc_page_live_slots(page);

    int cls = page->head.mutable ? 1 : 0;
    gc_occ_pages[cls] += 1;
    gc_occ_live[cls]  += live_slots;
    if (live_slots * 4 < SLOTS_PER_PAGE) {
        gc_occ_sparse[cls]      += 1;
        gc_occ_sparse_free[cls] += SLOTS_PER_PAGE - live_slots;
        if (cls == 0) {
            if      (page->head.compacted)     gc_occ_sparse_fwd += 1;
            else if (page->head.scanner.pinned) gc_occ_sparse_pin += 1;
            else                                gc_occ_sparse_oth += 1;
        }
    }
}

static NOINLINE_DEBUG gc_page_t* gc_page_alloc(unsigned page_count) {
    gc_stats_tick();
    if (!gc_debug_manual_mode) {
        // The collection rate is linked directly to the allocation rate:
        // one gc_fsa step per page allocated, its work drawn from the
        // allocation-clock credit (see the pacing comment at the top). Safe
        // points do no work of their own — a missed fsa_lock is recorded as
        // catch-up debt and repaid one step per safe point, so contended
        // steps are deferred rather than lost.
        if (!gc_fsa()) {
            gc_thread_info.lag_counter += 1;
            if (gc_thread_info.lag_counter > GC_PACE_LAG_MAX)
                gc_thread_info.lag_counter = GC_PACE_LAG_MAX;
            atomic_fetch_or(&gc_alloc_tl.safe_point_request, GC_SAFE_POINT_CATCH_UP);
        }

        // Relocation reserve: ordinary allocation may not consume the last
        // pages of the heap. Compaction frees sparse pages by evacuating
        // their survivors into NEW pages; with no headroom it cannot run and
        // a nearly-full heap deadlocks — pages cannot be freed because
        // freeing them needs pages — then aborts, even with most of the heap
        // reclaimable. When an ordinary allocation would dip into the
        // reserve, BLOCK: drive the collector synchronously until the heap
        // recovers. This is the structural pacing's full-heap regime — the
        // fixed scan/prune ratios never accelerate, so a nearly-full heap is
        // handled by stalling the allocator, not by collecting faster. Give
        // up only when collection stops helping: two complete cycles without
        // the used count reaching a new low means the heap is genuinely full
        // of live data, so proceed and let the allocator's own OOM abort
        // stand. Relocation allocations bypass the gate (that is the
        // reserve's purpose). The iteration bound keeps a stuck FSA (e.g. a
        // root scan waiting on a wedged thread, cycles never completing) an
        // OOM rather than a hang.
        if (!gc_thread_info.in_relocation && stage != GC_STAGE_NOT_STARTED) {
            size_t total   = memory_total_pages();
            // Ordinary allocation stalls FOUR reserves above the relocation
            // reserve itself: the gap absorbs allocator races past this
            // check (several threads can pass it before any of them claims
            // pages) and keeps compaction's own allocations — which bypass
            // the gate — out of competition with the mutators. The margin
            // need not cover the in-cycle overshoot: stalled mutators stop
            // the overshoot, the driven cycle completes, prune frees, and
            // the stall ends.
            size_t reserve = 4 * (total / 64 > 64 ? total / 64 : 64);
            size_t   lowest       = memory_count();
            uint64_t lowest_cycle = atomic_load(&gc_cycle_count);
            for (size_t spin = 0;
                 memory_count() + page_count > total - reserve && spin < (1u << 22);
                 spin++) {
                gc_fsa();
                size_t   used  = memory_count();
                uint64_t cycle = atomic_load(&gc_cycle_count);
                if (used < lowest) {
                    lowest       = used;   // collection is making headway —
                    lowest_cycle = cycle;  // keep driving
                } else if (cycle >= lowest_cycle + 2) {
                    break;
                }
            }
        }
    }

    atomic_fetch_add_explicit(&gc_alloc_clock, page_count, memory_order_relaxed);

    // memory_pages_alloc hands back pages with UNDEFINED contents (see
    // claimed_run): the header must be zeroed here, and object slots are
    // zeroed individually at allocation in object_alloc_fast. The release fence
    // orders the header zeroing before the tag store — the conservative
    // scanner probes arbitrary candidate pages by tag, and must never see
    // the magic number ahead of zeroed bitmaps. (gc_page_free clears the tag
    // before releasing the pages, so stale magic cannot pre-date this store.)
    gc_page_t *page = memory_pages_alloc(page_count);
    memset(&page->head, 0, sizeof(page_head_t));
    page->head.pages = page_count;
    page->head.stable_since = UINT64_MAX;   // "never pruned": the first prune
                                            // starts the stability clock
    atomic_thread_fence(memory_order_release);
    page->head.tag = PAGE_MAGIC_NUMBER;

    LOG(TRACE, "gc_page_alloc(%d) = 0x%lx", page_count, (uintptr_t)page);

    return page;
}

static NOINLINE_DEBUG void gc_page_free(gc_page_t* page) {
    GC_STAT_BUMP(gc_stat_pages_freed);
    assert(page->head.tag == PAGE_MAGIC_NUMBER);
    LOG(TRACE, "gc_page_free(%d) = 0x%lx", page->head.pages, (uintptr_t)page);

    // Straight back to mmap. A stale conservative stack slot that still
    // resolves into this page is handled by the scanner's own checks (FREE
    // marker, zeroed tag during re-initialisation, zeroed objects bitmap on
    // reuse) — see gc_object_is_on_heap_slow.
    page->head.tag = 0;
    memory_pages_free(page, page->head.pages);
}


static void object_get_page_and_slot(object_t* ptr, gc_page_t** page_out, ptrdiff_t* slot_out) {
    *page_out = (gc_page_t*)((intptr_t)ptr & ~(sizeof(gc_page_t)-1));
    *slot_out = (slot_t*)ptr - (*page_out)->slots;
    assert( (*page_out)->head.tag == PAGE_MAGIC_NUMBER );
    assert( (*slot_out) >= 0 && (*slot_out) < SLOTS_PER_PAGE );
}


static void default_roots_declaration_func() { }
static roots_declaration_func_t declare_roots_yafl = default_roots_declaration_func;
EXPORT roots_declaration_func_t add_roots_declaration_func(roots_declaration_func_t f) {
    roots_declaration_func_t previous = declare_roots_yafl;
    declare_roots_yafl = f;
    return previous;
}

// The allocation FAST PATH (object_alloc_fast / object_new / zero_object_slots)
// lives in yafl.h and inlines into generated code. This is its slow half:
// multi-page objects, and bump-region refill — where the GC pacing clock ticks
// (gc_page_alloc). Refill then re-runs the fast path, which now succeeds (a
// fresh page's slot region is exactly MAX_OBJECT_SIZE). RAW: no zeroing here —
// object_alloc_fast zeroes at its call site (where the C compiler can elide),
// and array_create's pointer-free path zeroes the header slots alone.
EXPORT void *object_alloc_slow_raw(size_t size, bool is_mutable) {
    size_t actual_size = (size + sizeof(slot_t) - 1) / sizeof(slot_t) * sizeof(slot_t);

    if (actual_size > MAX_OBJECT_SIZE) {
        // Object exceeds a single page's slot region: allocate a dedicated
        // multi-page run and treat the whole slot region as one object. Only
        // bit 0 of the head page's `objects` bitmap is set; subsequent
        // physical pages have no header of their own.
        size_t page_count = (sizeof(page_head_t) + actual_size + GC_PAGE_SIZE - 1) / GC_PAGE_SIZE;
        gc_page_t* page = gc_page_alloc(page_count);
        page->head.mutable = is_mutable;
        page->head.objects.a[0] = 1;
        list_link(&gc_thread_info.new_pages, (list_element_t*)&page->head.list);
        // Snapshot-smear guard — see object_alloc_fast_raw for the rationale.
        if (UNLIKELY(gc_alloc_tl.safe_point_request & GC_SAFE_POINT_SCAN_ROOTS))
            atomic_bitmap_fetch_set(&page->head.scanner.atomic_seen, 0);
        return page->slots;
    }

    gc_page_t* new_page = gc_page_alloc(1);
    new_page->head.mutable = is_mutable;

    bump_pointers_t *bp = is_mutable
        ? &gc_alloc_tl.region_mutable
        : &gc_alloc_tl.region_immutable;
    bp->base = (char*)(new_page->slots);
    bp->bump = (char*)(new_page->slots + SLOTS_PER_PAGE);

    list_link(&gc_thread_info.new_pages, (list_element_t*)&new_page->head.list);

    return object_alloc_fast_raw(size, is_mutable);
}

EXPORT void* object_create(vtable_t *vtable) {
    assert(vtable->array_el_size == 0);
    // Every field is zero on return from object_new (the fast path zeroes the
    // object's slots). That NULL state is load-bearing — the generated code
    // writes each pointer field through the GC write barrier, which marks the
    // field's PRIOR value, and a partially-initialised object may be scanned;
    // NULL is safe, garbage is not.
    object_t *object = (object_t*)object_new(vtable);
    LOG(ULTRA, "ALLOC(0x%lx) -> %s", (uintptr_t)object, vtable->name);
    return object;
}

EXPORT void* array_create(vtable_t *vtable, int32_t length) {
    assert(length >= 0);
    assert(vtable->array_el_size != 0);
    size_t total = vtable->object_size + (size_t)vtable->array_el_size * (size_t)length;
    object_t *object;
    if (vtable->array_el_pointer_locations == 0) {
        // Pointer-free payload (byte/int/float arrays — file buffers, string
        // storage): every GC element scan gates on the element mask, so the
        // payload's zero state is load-bearing for NOTHING. Skip the fill —
        // the dominant memset for large IO buffers that are overwritten
        // immediately — and zero only the HEADER's slots (vtable, length and
        // any scalar fields; rounding into the first payload bytes is
        // harmless). The caller's contract is write-before-read on elements,
        // which YAFL_GC_POISON makes loud if ever violated.
        object = (object_t*)object_alloc_fast_raw(total, vtable->is_mutable);
        size_t header = ((size_t)vtable->object_size + sizeof(slot_t) - 1)
                        / sizeof(slot_t) * sizeof(slot_t);
        zero_object_slots(object, header);
    } else {
        // Pointer-bearing elements: the whole object must be zero — it may be
        // scanned before every element is written (the fill loop can suspend),
        // and NULL is safe where garbage is not.
        object = (object_t*)object_alloc_fast(total, vtable->is_mutable);
    }
    object->vtable = vtable_tag(vtable);
    *((int32_t*)(((char*)object)+(vtable->array_len_offset))) = length;
    LOG(ULTRA, "ALLOC(0x%lx) -> %s", (uintptr_t)object, vtable->name);
    return object;
}






EXPORT size_t object_get_size(object_t* ptr) {
    size_t size;
    vtable_t* vt = object_get_vtable(ptr);
    if (vt->array_len_offset) {
        uint32_t len = *(uint32_t*)&((char*)ptr)[vt->array_len_offset];
        size = vt->object_size + vt->array_el_size*len;
    } else {
        size = vt->object_size;
    }
    size_t actual_size = (size + sizeof(slot_t) - 1) / sizeof(slot_t) * sizeof(slot_t);
    return actual_size;
}

// ── ListBuilder support ──────────────────────────────────────────────────────
// In-order list construction (stdlib ListBuilder): cells are ordinary
// immutable ChainLinks; the ONE mutable step — writing the previous tail's
// `next` — happens here, on a cell that is PINNED (compaction never moves
// it) and not yet published (linearity: only the builder can reach it).
// `next` is the LAST field of every ChainLink<T> instantiation (the value's
// representation varies, the trailing pointer slot does not), so the slot is
// object_size - sizeof(void*) from the cell base. No write barrier: under
// SATB the barrier snapshots the OLD value, and the old value here is the
// ChainEnd terminator the cell was constructed with — a static.
EXPORT bool list_builder_pin(object_t *cell) {
    object_pin(cell);
    return true;
}

// The `next` slot index for this instantiation's cells: the TRAILING pointer
// field = the highest set bit of the pointer mask (object_size is slot-
// rounded and can land in padding; the mask indexes 8-byte slots from the
// object base, vtable at bit 0). Computed ONCE per builder — the layout is
// constant per instantiation — and carried in the builder; per-push linking
// is then a single indexed store.
EXPORT int64_t list_builder_slot(object_t *cell) {
    vtable_t *vt = vtable_untag(cell->vtable);
    ptr_mask_t mask = vt->object_pointer_locations;
    return (int64_t)(63 - (unsigned)__builtin_clzll(mask));
}

EXPORT bool list_builder_link(object_t *prev, object_t *cell, int64_t slot) {
    ((object_t**)prev)[slot] = cell;             // prev pinned ⇒ address stable
    object_unpin(prev);                          // prev is now frozen
    return true;
}

EXPORT bool list_builder_seal(object_t *tail) {
    object_unpin(tail);
    return true;
}

// ── late pinning ─────────────────────────────────────────────────────────────
// Taking the pin on an object that is already published, so that a write-once
// field can be filled in without the object being exiled from relocation and
// promotion for the rest of its life. The bit is a MUTEX with exactly one
// owner: a peer writer, or the compactor claiming the object to evacuate it.

// Set whenever a late write lands on an `old` page, so the start of the next
// cycle knows whether the old-generation walk below is worth doing at all.
// Without it every cycle would pay a list traversal of the whole old
// generation (12k+ pages on a self-compile) to discover nothing.
static _Atomic(bool) gc_redirty_requested = false;

static bool gc_object_is_on_heap_fast(object_t *object);   // defined with the marker

EXPORT object_t* object_pin_resolve(object_t* o) {
    for (;;) {
        // Resolve relocation FIRST and afresh on every attempt: the write must
        // land on the copy the rest of the world will read, and the chain can
        // grow while we are waiting.
        vtable_t *vt = o->vtable;
        while (UNLIKELY(vtable_is_forward(vt))) {
            o  = (object_t*)vt;
            vt = o->vtable;
        }
        if (object_try_pin(o))
            return o;
        // Every possible holder releases after a bounded, allocation-free
        // section, so spinning is right and back-off would only add latency.
        __builtin_ia32_pause();
    }
}

EXPORT void gc_note_late_write(object_t* o) {
    if (!gc_object_is_on_heap_fast(o))
        return;                                  // static or tagged: not ours
    gc_page_t *page = (gc_page_t*)((uintptr_t)o &~ (uintptr_t)(GC_PAGE_SIZE-1));
    // Dekker handshake with the promotion decision (gc_fsa_prune_body): each
    // side WRITES its flag, fences, then READS the other's, so at least one
    // of them must observe the other. Checking `old` first — as this
    // originally did — is check-then-act: prune's refs walk can pass this
    // object before the pin lands and set `old` after the check read it as
    // false, promoting a page whose young referent nothing would ever trace.
    // So the flag is set UNCONDITIONALLY, young pages included: a young
    // page's stale flag costs one spurious dirty_old round at its eventual
    // promotion attempt (the exchange there consumes it), never correctness.
    atomic_store_explicit(&page->head.redirty, true, memory_order_relaxed);
    atomic_thread_fence(memory_order_seq_cst);
    if (!page->head.old)
        return;         // in the rotation, or mid-promotion — in which case
                        // the promoter's own re-check sees the flag we set
    atomic_store_explicit(&gc_redirty_requested, true, memory_order_release);
}

// Exported out-of-line alias of the inline accessor (yafl.h) for any caller
// that takes its address or links against the symbol.
#undef object_get_vtable
EXPORT vtable_t *object_get_vtable(object_t *object) {
    return object_get_vtable_inline(object);
}
#define object_get_vtable object_get_vtable_inline

EXPORT fun_t object_lookup_vtable(object_t *object, intptr_t id) {
    vtable_t* vtable = object_get_vtable(object);
    intptr_t index = id & vtable->functions_mask;   // byte offset into lookup[]
    vtable_entry_t* entry = (vtable_entry_t*)((char*)vtable->lookup + index);
    // Signed arithmetic is important here: blank entries hold id -1, so a miss
    // walks on until it reaches the abort handler the vtable plants — a safety
    // feature that costs us nothing. Probe from `index` until the ids match.
    while ((entry->i ^ id) > 0) entry++;
    return (fun_t){.f=entry->f, .o=object};
}



static bool gc_change_thread_state(struct gc_thread_info *thread_info, enum thread_state expected, enum thread_state desired) {
  return atomic_compare_exchange_strong(&thread_info->thread_state, &expected, desired);
}

static NOINLINE void gc_update_stack_address_and_registers() {
    object_t* some_random_var = NULL;
#ifdef STACK_GROWS_DOWN
    gc_thread_info.stack_lower_ptr = &some_random_var;
#else
    thread->stack_upper_ptr = &some_random_var;
#endif
    setjmp(gc_thread_info.saved_registers);
    // setjmp pointer-mangles rbp (see gc_internal.h): dump the callee-saved
    // set raw so an object referenced only from a register still pins.
#if defined(__x86_64__)
    void** r = gc_thread_info.saved_callee_regs;
    __asm__ volatile(
        "mov %%rbx,  0(%0)\n\t"
        "mov %%rbp,  8(%0)\n\t"
        "mov %%r12, 16(%0)\n\t"
        "mov %%r13, 24(%0)\n\t"
        "mov %%r14, 32(%0)\n\t"
        "mov %%r15, 40(%0)\n\t"
        :: "r"(r) : "memory");
    r[6] = r[7] = NULL;
#elif defined(__aarch64__)
    void** r = gc_thread_info.saved_callee_regs;
    register void* x19 __asm__("x19"); register void* x20 __asm__("x20");
    register void* x21 __asm__("x21"); register void* x22 __asm__("x22");
    register void* x23 __asm__("x23"); register void* x24 __asm__("x24");
    register void* x25 __asm__("x25"); register void* x26 __asm__("x26");
    r[0]=x19; r[1]=x20; r[2]=x21; r[3]=x22; r[4]=x23; r[5]=x24; r[6]=x25; r[7]=x26;
    // x27/x28/x29 arrive via the setjmp buffer (unmangled on aarch64 glibc).
#else
    memset(gc_thread_info.saved_callee_regs, 0, sizeof gc_thread_info.saved_callee_regs);
#endif
}

// Start of potentially thread pausing IO
EXPORT void gc_io_begin() {
    LOG(TRACE, "io_begin");

    // Don't call object_gc_safe_point(), because things then get recursive

    assert(gc_thread_info.thread_state == THREAD_STATE_RUNNING);

    gc_update_stack_address_and_registers();
    atomic_store(&gc_thread_info.thread_state, THREAD_STATE_SUSPENDED);
}

// End of potentially thread pausing IO
EXPORT void gc_io_end() {
    LOG(TRACE, "io_end");

    do {
        // Load the state ONCE per spin. Comparing the atomic field twice
        // (as `state == A || state == B` does) races the scanner's
        // SUSPENDED_SCAN -> SUSPENDED restore: the first load can see
        // SUSPENDED_SCAN and the second SUSPENDED, failing both arms of a
        // perfectly legal transition.
        enum thread_state st = atomic_load(&gc_thread_info.thread_state);
        assert(st == THREAD_STATE_SUSPENDED || st == THREAD_STATE_SUSPENDED_SCAN);
        (void)st;
    } while (!gc_change_thread_state(&gc_thread_info, THREAD_STATE_SUSPENDED, THREAD_STATE_RUNNING));
}

// Any thread that can do allocation must call this early on. `stack_anchor`
// must point at a local in the CALLING frame (or shallower): it becomes the
// fixed end of this thread's conservative stack-scan window, so it must sit
// above every frame the thread will ever run managed work in. Capturing a
// local inside THIS function is wrong — this frame dies on return, the very
// next call from the caller reuses the region, and the top slice of that
// callee's frame then lies OUTSIDE the window (observed: a pinned local
// 8 bytes above it, never scanned — found by test_gc_fwd_chain).
EXPORT void gc_declare_thread(thread_roots_declaration_func_t thread_roots_declaration_func, void*thread_roots_context, object_t** stack_anchor) {
    yafl_stack_guard_init();   // turn a stack overflow on this thread into a clean error
    yafl_prof_thread_init();   // no-op unless the program ran yafl_prof_init (--profile)
    yafl_heapprof_thread_init();   // no-op unless YAFL_HEAPPROF is set
#ifdef STACK_GROWS_DOWN
    gc_thread_info.stack_upper_ptr = stack_anchor;
#else
    gc_thread_info.stack_lower_ptr = stack_anchor;
#endif

    gc_thread_info.thread_roots_declaration_func = thread_roots_declaration_func;
    gc_thread_info.thread_roots_context = thread_roots_context;

    gc_thread_info.next = threads;
    gc_thread_info.thread_state = THREAD_STATE_RUNNING;
    // Wire the collector's remote view of this thread's allocation state (the
    // public gc_alloc_tl thread-local the inline fast path uses).
    gc_thread_info.alloc = &gc_alloc_tl;

    gc_thread_info.new_pages.next = &gc_thread_info.new_pages;
    gc_thread_info.new_pages.prev = &gc_thread_info.new_pages;

    while (!atomic_compare_exchange_weak(&threads, &gc_thread_info.next, &gc_thread_info));
}

#if COMPACT_THRESHOLD_PERCENT > 0
static NOINLINE_DEBUG void gc_compact_page(gc_page_t *page) {
    const unsigned slots_threshold = SLOTS_PER_PAGE * COMPACT_THRESHOLD_PERCENT / 100;

    // Previously compacted. If we do it again we'll be making redundent copies.
    if (page->head.compacted)
        return;

    // Don't compact pages reachable from a conservative (stack/register) root:
    // those references can't be rewritten to follow the forwarding pointer, so
    // the original must stay put. `pinned` is set during root scanning and reset
    // when the page is pruned, so it reflects this cycle's conservative roots.
    if (page->head.scanner.pinned)
        return;

    // Don't compact these types of pages.
    if (page->head.mutable || page->head.pages > 1)
        return;
    // (Dirty-old pages CAN be compacted, and old referrers stay sound — by a
    // conspiracy worth recording: a dirty page's dead slots are frozen by its
    // force-mark, so it only goes sparse in a MAJOR's honest trace, and that
    // same major demoted every old referrer, which is then re-scanned — and
    // fixed up through the forwarding — while still young. The old-generation
    // purity validator (YAFL_GC_VALIDATE_OLD) guards this reasoning in test
    // builds.)

    // Don't compact pages with too many objects. This test is faster than counting up
    // the total size of all of the objects.
    if (bitmap_count(&page->head.objects) > slots_threshold)
        return;

    unsigned total = 0;
    unsigned object_count = 0;
    struct { uint16_t o; uint16_t s; } objects[slots_threshold];

    // Find size and offset of each object
    // If we hit the upper size threshold, abort the operation
    for (unsigned index = 0; index < sizeof(bitmap_t) / sizeof(mask_bits_t); ++index) {
        mask_bits_t bits = page->head.objects.a[index];
        unsigned offset = index * GC_MASK_SIZE;
        while (bits) {
            unsigned slot = __builtin_ctzll(bits) + offset;
            bits &= bits-1;

            // PINNED objects stay at their address: a runtime primitive is
            // mid-mutation on a raw pointer (see yafl.h object_pin). Leave it
            // out of the evacuation set; the page simply keeps serving it.
            object_t *candidate = (object_t*)&page->slots[slot];
            if (vtable_is_pinned(candidate->vtable)) {
                continue;
            }
            size_t size = object_get_size(candidate);
            objects[object_count].o = slot;
            objects[object_count].s = size;
            object_count += 1;

            total += size;
            if (total > slots_threshold*sizeof(slot_t))
                return; // Too big for compaction, this time
        }
    }

    // Copy each object to newly allocated space. Flag the thread so these
    // target allocations may use the relocation reserve — they are the one
    // class of allocation that must succeed near full, because each evacuated
    // page returns more pages than the evacuation consumed.
    page->head.compacted = true;
    bool was_in_relocation = gc_thread_info.in_relocation;
    gc_thread_info.in_relocation = true;
    for (unsigned index = 0; index < object_count; ++index) {
        object_t *object = (object_t*)&page->slots[objects[index].o];
        size_t      size = objects[index].s;

        // Target FIRST, claim second. The pin bit is a mutex shared with late
        // writers (yafl.h object_try_pin), so the window between claiming and
        // publishing the forward word is time a writer may spend spinning —
        // it must contain no allocation. A target that goes unused because
        // the claim lost is ordinary garbage, collected next cycle; that only
        // happens under genuine contention, which is rare.
        object_t *target = (object_t*)object_alloc_fast(size, false);

        // Claim: CAS the vtable word to pinned. Fails if a mutator holds the
        // pin (mid-write — leave the object where it is, exactly as the
        // pre-scan's pinned check does) or if the word already forwards.
        if (!object_try_pin(object))
            continue;

        // Drop the PIN only: the vtable TAG must survive onto the copy, or the
        // copy's own header would read as a forwarding pointer.
        vtable_t *vt = (vtable_t*)((uintptr_t)object->vtable & ~(uintptr_t)VTABLE_PIN_BIT);
        memcpy(target, object, size);
        // The memcpy copied the CLAIMED word, pin bit and all. Clear it on the
        // copy before anyone can reach it — the target is still private here,
        // so a plain store is enough.
        target->vtable = vt;
        // Publish the forwarding pointer, releasing the copy's contents: a
        // reader that follows this word must see a fully written object. The
        // store also drops the pin (a heap address has bit 0 clear), handing
        // the object over to the lazy-fixup protocol.
        __atomic_store_n((uintptr_t*)&object->vtable, (uintptr_t)target,
                         __ATOMIC_RELEASE);
    }
    gc_thread_info.in_relocation = was_in_relocation;
}
#endif








bool gc_object_is_on_heap_slow(object_t *object) {
    uintptr_t asint = (uintptr_t)object;
    gc_page_t *page = (gc_page_t*)(asint &~ (GC_PAGE_SIZE-1));
    return object != NULL                     // Must have a non-zero value
        && (asint & (GC_SLOT_SIZE-1)) == 0    // Pointer aligns with slot boundaries
        && memory_pages_is_alloc_head(object)  // Pointer lands on a real page on managed heap
        // Page header carries the live magic tag. A conservative candidate can
        // be a stale stack slot pointing into a page that is being drained
        // (tag already zeroed, marker not yet FREE) or re-initialised (marker
        // HEAD, tag not yet written) by a concurrent gc_page_alloc — such a
        // page holds no live objects, so rejecting it is always correct.
        && page->head.tag == PAGE_MAGIC_NUMBER
        && (asint & (GC_PAGE_SIZE-1)) >= offsetof(gc_page_t, slots)             // Does NOT point into the page header
        && bitmap_test(&page->head.objects, ((slot_t*)object) - page->slots);   // Is a real and exists object in this page
}

static bool gc_object_is_on_heap_fast(object_t *object) {
    // One unsigned compare covers NULL (wraps to huge), static objects
    // (outside the mmap region) and wild values — WITHOUT touching the
    // candidate object's memory. This range check is also what lets the
    // vtable word be an ordinary pointer: heap-vs-static needs no tag bit.
    return ((intptr_t)object & PTR_TAG_MASK) == 0          // No packed data: rejects PTR_TAG_TASK (0x1), PTR_TAG_INTEGER (0x2), and PTR_TAG_STRING (0x4)
        && (size_t)((char*)object - _memory_heap_base) < _memory_heap_bytes;
}

static NOINLINE_DEBUG void atomic_gc_object_mark_as_seen(object_t *object) {
    gc_page_t* page; ptrdiff_t slot;
    object_get_page_and_slot(object, &page, &slot);
    assert(bitmap_test(&page->head.objects, slot));
    if (page->head.old) return;   // old generation: implicitly live in minor cycles
    bool is_seen = bitmap_test(&page->head.scanner.seen, slot);
    if (!is_seen) {
        if (!atomic_bitmap_fetch_set(&page->head.scanner.atomic_seen, slot)

            // If it's not "processsed" we don't need to do anything
            // If it's not in the scanning list at all, definately don't do anything

            // New pages have 'processsed_by_epoch==0', as do pages relocated to the to_scan list
            // After a bulk move, the epoch is incremented, so it won't match historicaly processed pages anyway

            && page->head.scanner.processed_by_epoch == epoch) {

            for (size_t scan_index = 0; scan_index < sizeof(reprocess_page_list) / sizeof(gc_page_t*); ++scan_index)
                if (reprocess_page_list[scan_index] == page)
                    return;

            size_t tail = reprocess_page_tail;
            do {if (tail - reprocess_page_head >= sizeof(reprocess_page_list) / sizeof(gc_page_t*)) {
                    atomic_store(&reprocess_overflow_flag, true);
                    return;
                }
            } while (!atomic_compare_exchange_strong(&reprocess_page_tail, &tail, tail+1));
            atomic_store(&reprocess_page_list[tail % REPROCESS_PAGE_COUNT], page);
        }
    }
}

static NOINLINE_DEBUG void atomic_gc_object_seen_by_field(object_t **field_ptr) {
    object_t *object = *field_ptr;
    while (gc_object_is_on_heap_fast(object)) {
        atomic_gc_object_mark_as_seen(object);
        if (LIKELY(!vtable_is_forward(object->vtable))) break;
        *field_ptr = object = (object_t*)object->vtable;
    }
}






#ifdef YAFL_GC_VALIDATE_OLD
// Diagnostic walk (test builds): see the call site in gc_fsa_start.
static void gc_validate_old_edge(gc_page_t *page, object_t *object,
                                 object_t *child) {
    if (!gc_object_is_on_heap_fast(child)) return;
    gc_page_t *cp = (gc_page_t*)((uintptr_t)child &~ (uintptr_t)(GC_PAGE_SIZE-1));
    // Liveness first: the child's slot bit must be set in its page's object
    // bitmap. A page-flag check alone can be laundered — a dangling pointer
    // into a freed-and-recycled page reads whatever flags the new tenant
    // has. (Forwarded children excluse: the slot bit moves with the copy.)
    unsigned slot = (unsigned)(((uintptr_t)child - (uintptr_t)cp->slots) / GC_SLOT_SIZE);
    bool live = (uintptr_t)child >= (uintptr_t)cp->slots
             && bitmap_test(&cp->head.objects, slot);
    if (live && (cp == page || cp->head.old || cp->head.dirty_old)) return;
    if (live && vtable_is_forward(child->vtable)) return;
    if (atomic_load_explicit(&page->head.redirty, memory_order_relaxed)) return;
    if (!live) fprintf(stderr, "[VALIDATE_OLD] DEAD TARGET (slot bit clear)\n");
    fprintf(stderr, "[VALIDATE_OLD] cycle=%llu old page %p obj %p -> child %p "
            "on page %p (old=%d dirty=%d compacted=%d mutable=%d redirty=%d) "
            "child vtable word=%p forward=%d\n",
            (unsigned long long)atomic_load(&gc_cycle_count),
            (void*)page, (void*)object, (void*)child, (void*)cp,
            cp->head.old, cp->head.dirty_old, cp->head.compacted,
            cp->head.mutable,
            (int)atomic_load_explicit(&cp->head.redirty, memory_order_relaxed),
            (void*)child->vtable, (int)vtable_is_forward(child->vtable));
    fflush(stderr);
    abort();
}

static void gc_validate_old_pages(void) {
    gc_pool_lock();
    for (list_element_t *node = old_pages.next; node != &old_pages; node = node->next) {
        gc_page_t *page = (gc_page_t*)node;
        for (unsigned index = 0; index < sizeof(bitmap_t) / sizeof(mask_bits_t); ++index) {
            mask_bits_t bits = page->head.objects.a[index];
            unsigned  offset = index * GC_MASK_SIZE;
            while (bits) {
                unsigned slot = __builtin_ctzll(bits) + offset;
                bits &= bits-1;
                object_t *object = (object_t*)&page->slots[slot];
                vtable_t *vt = vtable_untag(object->vtable);
                GC_FOR_EACH_PTR_WINDOW(vt, object, m, slots)
                while (m) {
                    unsigned i = __builtin_ctzll(m); m &= m-1;
                    gc_validate_old_edge(page, object, slots[i]);
                }
                if (vt->array_el_pointer_locations) {
                    uint32_t len = *(uint32_t*)&((char*)object)[vt->array_len_offset];
                    char*  array = ((char*)object) + vt->object_size;
                    for (; len-- > 0; array += vt->array_el_size) {
                        ptr_mask_t am = vt->array_el_pointer_locations;
                        while (am) {
                            unsigned i = __builtin_ctzll(am); am &= am-1;
                            gc_validate_old_edge(page, object, ((object_t**)array)[i]);
                        }
                    }
                }
            }
        }
    }
    gc_pool_unlock();
}
#endif

static NOINLINE_DEBUG enum gc_stage gc_fsa_start() {
    if (++epoch == 0)
        epoch = 1;

    // Pages a late write touched while they were `old`: return them to the
    // rotation BEFORE this cycle's decisions, so the young objects those
    // writes installed are traced from here on. Marked dirty_old rather than
    // merely young, because the referent is young by definition and the page
    // must be force-marked as a root until it has caught up. Gated on the
    // global so the common case — no late writes — costs one atomic read.
    if (UNLIKELY(atomic_exchange_explicit(&gc_redirty_requested, false,
                                          memory_order_acquire))) {
        gc_pool_lock();
        for (list_element_t *node = old_pages.next; node != &old_pages; ) {
            gc_page_t *p = (gc_page_t*)node;
            node = node->next;               // saved: the unlink below clears it
            if (!atomic_exchange_explicit(&p->head.redirty, false,
                                          memory_order_relaxed))
                continue;
            p->head.old       = false;
            p->head.dirty_old = true;
            p->head.refs_defer = p->head.refs_backoff = 0;
            list_unlink((list_element_t*)&p->head.list);
            list_link(&pages_to_scan, (list_element_t*)&p->head.list);
            atomic_fetch_sub_explicit(&gc_old_page_count, 1, memory_order_relaxed);
        }
        gc_pool_unlock();
    }

#ifdef YAFL_GC_VALIDATE_OLD
    // Diagnostic (test builds only): the old-generation purity invariant,
    // checked at every cycle start. Every outgoing reference of every object
    // on a fully-OLD page must land on an old, dirty-old, or non-heap target
    // — except when the source page's redirty flag is up, which is a late
    // write's pending demotion (handled just above on the NEXT cycle). An
    // old->young edge with no flag is the state that lets a minor reclaim a
    // live object; catching it here names the breaking cycle instead of the
    // crash a hundred cycles later.
    gc_validate_old_pages();
#endif

    // Major-cycle decision: collect the old generation when it has doubled
    // since the last major (floored), under heap pressure, or on request.
    // The generation's size INCLUDES dirty-old pages: they are retained old
    // data that merely hasn't graduated to fully-exempt yet. Counting only
    // the clean set creates a feedback loop — a major demotes everything,
    // re-promotion lands in dirty, the baseline records ~zero, and the next
    // promotion wave immediately re-triggers a major, forever.
    {
        size_t old_total = gc_old_page_count + gc_dirty_old_count;
        size_t pressure  = memory_total_pages() / 2;
        size_t doubled   = gc_old_baseline * 2;
        gc_major_cycle = gc_major_request
            || (old_total >= GC_MAJOR_FLOOR && old_total >= doubled)
            || (pressure != 0 && memory_count() > pressure);
        gc_major_request = false;
        if (gc_major_cycle) {
            // Demote the whole old generation into this cycle's rotation.
            // Flags are cleared BEFORE gc_write_barrier_requested goes up, so
            // no mark source can observe old=true on a page that is back in
            // the rotation and skip a mark it owes.
            for (list_element_t *node = old_pages.next; node != &old_pages; node = node->next)
                ((gc_page_t*)node)->head.old = false;
            list_move(&pages_to_scan, &old_pages);
            gc_old_page_count = 0;
        }
    }

    gc_cycle_survivors = 0;   // accumulated through this cycle's PRUNE stage
    gc_cycle_survivor_slots = 0;
    mark_worklist_reset();    // already empty (drained per page); defensive
    memset(gc_occ_pages, 0, sizeof gc_occ_pages);   // page-occupancy survey accumulators
    memset(gc_occ_live,  0, sizeof gc_occ_live);
    memset(gc_occ_sparse, 0, sizeof gc_occ_sparse);
    memset(gc_occ_sparse_free, 0, sizeof gc_occ_sparse_free);
    gc_occ_large = 0;
    gc_occ_sparse_fwd = gc_occ_sparse_pin = gc_occ_sparse_oth = 0;

    gc_write_barrier_requested = true;
    reprocess_page_head = reprocess_page_tail = 0;
    memset(reprocess_page_list, 0, sizeof(reprocess_page_list));

    // EARLY declared-roots pass, with the deletion barrier already ON: the
    // SATB root snapshot. A late-only read (end of SCAN_ROOTS) is unsound —
    // a ratcheting root moves onto a birth-protected page between a
    // thread's take and any later read, hiding the chain's tail on taken
    // pages: the test_gc_pressure DANGLE. From this point on, root
    // MUTATIONS carry an obligation, exactly as heap fields do:
    // gc_root_overwrite shades a slot's outgoing occupant, gc_root_publish
    // shades a value published into a root that its thread may drop before
    // its take-time stack scan. See yafl.h, "The mutable-root contract".
    declare_roots_yafl(atomic_gc_object_seen_by_field);
    declare_roots_thread(atomic_gc_object_seen_by_field);

    for (struct gc_thread_info *thread = threads; thread != NULL; thread = thread->next) {
        atomic_fetch_or(&thread->alloc->safe_point_request, GC_SAFE_POINT_SCAN_ROOTS);
        thread->roots_scanned = false;
    }

    return GC_STAGE_SCAN_ROOTS;
}






// Highest set bit ≤ slot in `bm`, or -1. The conservative scan's
// interior-pointer resolution: the containing object is the nearest object
// START at or before the addressed slot.
static inline long bitmap_prev_set(const bitmap_t* bm, long slot) {
    long wi = slot / GC_MASK_SIZE;
    long bi = slot % GC_MASK_SIZE;
    mask_bits_t w = bm->a[wi];
    if (bi != GC_MASK_SIZE - 1)
        w &= (((mask_bits_t)1 << (bi + 1)) - 1);
    for (;;) {
        if (w) return wi * GC_MASK_SIZE + (GC_MASK_SIZE - 1 - (long)__builtin_clzll(w));
        if (--wi < 0) return -1;
        w = bm->a[wi];
    }
}

static NOINLINE_DEBUG void gc_fsa_scan_roots$scan_range(object_t **range_ptr, object_t **range_end) {
    for (; range_ptr != range_end; range_ptr++) {
        object_t *object = *range_ptr;
        // Conservative candidate — INTERIOR POINTERS INCLUDED. An optimising
        // C compiler may keep only a derived pointer live (a rolling
        // &obj->items[i] in a register) while the base pointer is dead; the
        // object is still reachable, so an exact-base-only scan frees live
        // objects (test_large_objects: the root array survived only as an
        // interior pointer at -O2 and was pruned). Resolution: any 8-aligned
        // address inside a live allocation — head page or a run's body pages
        // — marks the nearest object START at or before it. A stale integer
        // that happens to resolve costs over-retention, never a miss; a
        // candidate racing a page drain hits FREE markers or a dead tag and
        // is rejected, which is always correct because live pages are never
        // freed. The reprocess-queue handling that atomic_gc_object_mark_as_
        // seen does is not needed here: during SCAN_ROOTS no page has been
        // mark-swept this epoch yet.
        if (object == NULL
            || ((uintptr_t)object & (sizeof(void*) - 1)) != 0
            || (size_t)((char*)object - _memory_heap_base) >= _memory_heap_bytes)
            continue;
        gc_page_t* page = (gc_page_t*)memory_pages_alloc_head_of(object);
        if (page == NULL || page->head.tag != PAGE_MAGIC_NUMBER)
            continue;
        ptrdiff_t byte_off = (char*)object - (char*)page->slots;
        if (byte_off < 0)
            continue;   // points into the head page's header
        long slot = byte_off / GC_SLOT_SIZE;
        if (slot >= (long)SLOTS_PER_PAGE)
            slot = SLOTS_PER_PAGE - 1;   // run body page: the run head's last object covers it
        long containing = bitmap_prev_set(&page->head.objects, slot);
        if (containing < 0)
            continue;   // before the first object on the page
        if (page->head.old) continue;   // old generation: implicitly live, never pruned
        page->head.scanner.pinned = true;
        if (!atomic_bitmap_fetch_set(&page->head.scanner.atomic_seen, containing))
            GC_STAT_BUMP(gc_stat_cons_seeds);   // diagnostic: conservative root seeds
    }
}

static NOINLINE_DEBUG enum gc_stage gc_fsa_scan_roots() {
    struct gc_thread_info *thread;
    enum thread_state old_state;

    if (!gc_thread_info.roots_scanned) {
        old_state = THREAD_STATE_RUNNING;
        atomic_store(&gc_thread_info.thread_state, THREAD_STATE_SUSPENDED_SCAN);
        gc_update_stack_address_and_registers();
        thread = &gc_thread_info;
    } else {
        old_state = THREAD_STATE_SUSPENDED;
        for (thread = threads; thread != NULL; thread = thread->next)
            if (!thread->roots_scanned && gc_change_thread_state(thread, THREAD_STATE_SUSPENDED, THREAD_STATE_SUSPENDED_SCAN))
                break;
    }

    if (thread != NULL) {
        thread->roots_scanned = true;
        // Greedily take this thread's bump pages into the collection pool. Objects
        // it allocates AFTER this (region reset below) land on fresh pages that
        // are taken NEXT cycle — that is the birth protection. The take must be
        // prompt — it rides on GC_SAFE_POINT and gc_page_alloc driving the FSA —
        // so this cycle's objects land after it rather than straddling onto a
        // taken page.
        list_move(&pages_to_scan, &thread->new_pages);
        thread->alloc->region_immutable.base = thread->alloc->region_mutable.base = NULL;
        thread->alloc->region_immutable.bump = thread->alloc->region_mutable.bump = NULL;
        // Scan stack and registers
        gc_fsa_scan_roots$scan_range(thread->stack_lower_ptr, thread->stack_upper_ptr);
        gc_fsa_scan_roots$scan_range((object_t**)&thread->saved_registers[0], (object_t**)&thread->saved_registers[1]);
        gc_fsa_scan_roots$scan_range((object_t**)&thread->saved_callee_regs[0],
                                     (object_t**)&thread->saved_callee_regs[8]);
        // Thread library has some stuff
        thread->thread_roots_declaration_func(thread->thread_roots_context, atomic_gc_object_seen_by_field);
        // Release the thread state
        atomic_fetch_and(&thread->alloc->safe_point_request, ~GC_SAFE_POINT_SCAN_ROOTS);
        atomic_store(&thread->thread_state, old_state);
        thread->lag_counter = 0;
    }

    for (thread = threads; thread != NULL; thread = thread->next)
        if (!thread->roots_scanned)
            return GC_STAGE_SCAN_ROOTS;

    // The declared roots are NOT re-scanned here. They were read once, at
    // cycle open (gc_fsa_start), with the deletion barrier already on —
    // the SATB root snapshot (the original design). Root mutations after
    // that carry the obligation, exactly as heap fields do:
    // gc_root_overwrite / gc_root_publish (yafl.h, "The mutable-root
    // contract"); the scheduler queues, IO slots, the lazy-init machinery
    // and the C tests all comply. A late pass used to run here; an earlier
    // "the late pass is load-bearing" finding was an artefact of a broken
    // experiment that had deleted the EARLY pass calls — with the early
    // pass present, the whole suite (and 20-run pressure soaks) is green
    // without it.

    // Dirty-old pages (aged, but still referencing young pages) are roots: mark
    // every live object on them so their young targets get traced this cycle.
    // They are never pruned (fully seen), and prune graduates them to fully-
    // exempt `old` once all their targets have promoted.
    //
    // In a MAJOR cycle, demote them instead: the force-mark retains every
    // dead object on a dirty page, and a major that only demotes the clean
    // old list leaves that garbage immortal — under churn whose objects live
    // a few cycles (long enough to age, then die) dirty pages accumulate
    // until they fill the heap (observed: yspell held 9k+ dead dirty pages;
    // test_gc_pressure aborts a 64 MiB heap). Demoted pages are traced from
    // real roots like any other page and re-promote through prune if still
    // genuinely live. They are still COUNTED this cycle: the end-of-major
    // baseline must reflect the set that existed before collection, else the
    // doubling trigger re-arms at the floor and majors thrash.
    gc_dirty_old_count = 0;
    for (list_element_t *node = pages_to_scan.next; node != &pages_to_scan; node = node->next) {
        gc_page_t *page = (gc_page_t*)node;
        if (page->head.dirty_old) {
            gc_dirty_old_count += 1;
            if (gc_major_cycle) {
                page->head.dirty_old = false;
                page->head.refs_defer = page->head.refs_backoff = 0;
            } else {
                for (unsigned i = 0; i < sizeof(bitmap_t)/sizeof(mask_bits_t); ++i)
                    page->head.scanner.seen.a[i] |= page->head.objects.a[i];
            }
        }
    }

    if (list_empty(&pages_to_scan)) {   // instrumented assert (P1 debugging)
        fprintf(stderr, "[SCAN_ROOTS EMPTY] cycle=%llu epoch=%u in_flight=%d executors=%d prune_empty=%d in_use=%zu\n",
                (unsigned long long)atomic_load(&gc_cycle_count), epoch,
                atomic_load(&gc_pages_in_flight), atomic_load(&gc_stage_executors),
                (int)list_empty(&pages_to_prune), memory_count());
        fflush(stderr);
        abort();
    }
    assert(list_empty(&pages_to_prune));

    return GC_STAGE_MARK_SWEEP;
}





static void gc_fsa_mark_sweep$page_needs_scan(gc_page_t *page) {
    gc_pool_lock();
    // CLAIMED page (popped by an executor, on no list): do NOT touch it — its
    // links are stale-nulled and its bitmaps are owner-exclusive. Skipping is
    // sound: the marks this requeue is signalling live in atomic_seen, and
    // the owner's end-of-page re-merge reads exactly that bitmap and requeues
    // the page itself if anything landed.
    if (page->head.list.next == NULL) {
        // Hand the request to the owner instead of dropping it: a mark that
        // landed AFTER the owner's end-of-page re-merge has no other catch
        // point (its ring entry is being consumed right here).
        atomic_store(&page->head.scanner.requeue_pending, true);
        gc_pool_unlock();
        return;
    }
    GC_STAT_BUMP(gc_stat_requeued);
    page->head.scanner.processed_by_epoch = 0;
    list_unlink((list_element_t*)&page->head.list);
    list_link(&pages_to_scan, (list_element_t*)&page->head.list);
    gc_pool_unlock();
}

static void gc_fsa_mark_sweep$mark_object(object_t *object) {
    if (UNLIKELY(gc_stats_enabled)) gc_prof_ptrs++;
    // Mark the target object
    gc_page_t *page; ptrdiff_t slot;
    object_get_page_and_slot(object, &page, &slot);
    if (page->head.old) return;   // old generation: implicitly live in minor cycles

    // PARALLEL-MARKING DISCIPLINE: a scanner marks remote objects through
    // atomic_seen — the same lock-free route the mutator barrier uses — never
    // the plain `seen` bitmap, which only a page's CLAIMING scanner may touch
    // (merge + diff). The merge machinery that already absorbs mutator marks
    // absorbs scanner marks identically. The racy read of `seen` first is a
    // bounded-duplicate filter, not a correctness gate: seen bits are
    // monotonic within an epoch, so a stale 1 is impossible; a stale 0 merely
    // falls through to the atomic test.
    if (bitmap_test(&page->head.scanner.seen, slot)) return;
    // Same racy pre-filter against atomic_seen: a locked fetch_or costs a
    // store-buffer drain (~20-40 cycles) even uncontended — measured at 58%
    // of mark_object's cycles at T=12 — while an already-marked object needs
    // nothing. Reading 1 is decisive at that instant: the bit is either still
    // in atomic_seen or has been drained into seen by a merge, so the object
    // is recorded either way and the setter made the worklist decision.
    // Reading a stale 0 merely falls through to the fetch_set — and the load
    // has warmed the exact line the RMW then needs.
    if (bitmap_test(&page->head.scanner.atomic_seen, slot)) return;
    bool was_set = atomic_bitmap_fetch_set(&page->head.scanner.atomic_seen, slot);
    // Heap census: exactly once per live object per cycle, on the winning
    // first-mark (docs/heap-profiling-design.md).
    if (UNLIKELY(yafl_heapprof_enabled) && !was_set)
        yafl_heapprof_census((const struct vtable *)object_get_vtable(object),
                             object_get_size(object));

    // Newly marked on a page the scanner already finished this epoch: a
    // back-edge. Push the object for direct scanning — the per-page drain in
    // gc_fsa_mark_sweep resolves it (and anything it reaches) before the page
    // that found it is considered done. The mark set above keeps it live for
    // prune (which merges residual atomic bits) regardless of where it sits.
    if (!was_set && page->head.scanner.processed_by_epoch == epoch)
        mark_worklist_push(object);
}

// `fixup` controls whether a relocated child's field is snapped to the
// forwarding target. For an IMMUTABLE container the GC owns the field and snaps
// it (true). For a MUTABLE container the mutator may be writing the same slot in
// parallel (async state objects rewrite their coalesced array slots as they
// run); the GC must NOT store into it — a fixup write races the mutator and can
// clobber its update with the slot's previous occupant. It still marks through
// the whole forward chain so the original stays live; the mutator follows
// forwarding lazily on read.
static void gc_fsa_mark_sweep$scan_elements(object_t **base_ptr, ptr_mask_t pointer_locations, bool fixup) {
    // Single-pointer fast path — list nodes and other one-child shapes
    // dominate chain-heavy heaps; skip the batch machinery for them.
    if ((pointer_locations & (pointer_locations - 1)) == 0) {
        unsigned index = (unsigned)__builtin_ctzll(pointer_locations);
        object_t **ptr_ptr = &base_ptr[index];
        object_t *object = *ptr_ptr;
        while (gc_object_is_on_heap_fast(object)) {
            __builtin_prefetch(object, 0);
            gc_fsa_mark_sweep$mark_object(object);
            vtable_t *vt = object->vtable;
            if (LIKELY(!vtable_is_forward(vt)))
                break;
            object = (object_t*)vt;
            if (fixup) *ptr_ptr = object;
        }
        return;
    }
    // Two passes: first gather the heap children and prefetch their page
    // headers (where the mark bitmaps live), then mark them. The gather pass
    // issues all the independent loads up front so the header misses overlap
    // instead of serialising one per child.
    object_t **batch[64];
    unsigned   count = 0;
    for (ptr_mask_t m = pointer_locations; m; m &= m - 1) {
        unsigned index = __builtin_ctzll(m);
        object_t *object = base_ptr[index];
        if (gc_object_is_on_heap_fast(object)) {
            __builtin_prefetch(&((gc_page_t*)((uintptr_t)object &~ (uintptr_t)(GC_PAGE_SIZE-1)))->head.scanner, 1);
            __builtin_prefetch(object, 0);   // child body (vtable + first fields) —
                                             // the LIFO pops it next; start the line now
            batch[count++] = &base_ptr[index];
        }
    }

    for (unsigned i = 0; i < count; ++i) {
        object_t **ptr_ptr = batch[i];
        object_t *object = *ptr_ptr;

        while (gc_object_is_on_heap_fast(object)) {
            gc_fsa_mark_sweep$mark_object(object);

            // Apply any forwarding pointer if found
            vtable_t *vt = object->vtable;
            if (LIKELY(!vtable_is_forward(vt)))
                break;

            object = (object_t*)vt;
            if (fixup) *ptr_ptr = object;
        }
    }
}

// poison-mode dangle check: gc_debug.c

static void gc_fsa_mark_sweep$scan_object(object_t *object) {
    if (UNLIKELY(gc_stats_enabled)) gc_prof_objs++;
    if (UNLIKELY(gc_poison_enabled))
        gc_dbg_dangle_check(object);
    // Find the real vtable pointer (forwarding-aware; targets get marked too:
    // a mutator may have read any hop's address before we got here, so every
    // hop must survive this cycle).
    vtable_t *vt = object->vtable;
    if (UNLIKELY(vtable_is_forward(vt))) {
        object_t *tail = object;
        do {
            tail = (object_t*)vt;
            gc_fsa_mark_sweep$mark_object(tail);
            vt = tail->vtable;
        } while (vtable_is_forward(vt));
        // Path-compress: point every walked stub straight at the tail. Heap
        // FIELDS are already snapped to the tail as the trace rewrites them,
        // but the stubs' own forward words were not — and a head stub kept
        // alive by an unrewritable reference (a conservative stack slot)
        // re-marks every intermediate hop each cycle, so a chain could grow
        // a hop per compaction of its current tail, forever. Compressed,
        // the bypassed intermediates stop being marked and die naturally.
        // A racing mutator walk sees either the old word (further down the
        // same chain) or the tail — both valid, same as compaction's own
        // store of the forward word.
        for (object_t *hop = object; hop != tail; ) {
            object_t *next = (object_t*)hop->vtable;
            hop->vtable = (vtable_t*)tail;
            hop = next;
        }
    }
    // A PINNED object (a ListBuilder tail mid-construction) carries the pin
    // bit in its vtable word; every field read off a tagged vtable is
    // misaligned garbage — the scan would walk a nonsense pointer mask and
    // silently mark NONE of the object's real children (observed: a pinned
    // ChainLink's payload freed while the link lived). Strip it before use.
    // Pinned objects are never forwarders (compaction skips them), so this
    // cannot mask a forward word.
    vt = vtable_untag(vt);

    // A mutable container's pointer slots may be written by the mutator in
    // parallel with this scan, so the GC must not snap them to forwarding
    // targets (it would race / clobber the mutator's store). Mark through but
    // don't rewrite. `vt` is the resolved (forwarding-followed) vtable and
    // carries the same mutability bit object_create used to place the object on
    // a mutable page, so it is authoritative without a separate page lookup.
    // A PINNED object is mutable in the same sense — a ListBuilder tail whose
    // `next` the mutator may write in parallel — so its fields must not be
    // snapped either (pinned objects are never forwarded themselves, so the
    // raw vtable word test is safe here).
    bool fixup = !vt->is_mutable && !vtable_is_pinned(object->vtable);

    // Scan references. Windowed map: scan_elements takes a base + one mask
    // word, so each 64-slot window is one call (window 0 stays the inline
    // word — the overwhelmingly common single-window case is unchanged).
    if (vt->object_pointer_locations) {
        gc_fsa_mark_sweep$scan_elements((object_t**)object, vt->object_pointer_locations, fixup);
    }
    if (UNLIKELY(vt->object_pointer_masks != NULL)) {
        for (unsigned w = 1; w < vt->object_pointer_mask_words; w++) {
            if (vt->object_pointer_masks[w])
                gc_fsa_mark_sweep$scan_elements((object_t**)object + (size_t)w * 64,
                                                vt->object_pointer_masks[w], fixup);
        }
    }

    if (vt->array_el_pointer_locations) {
        uint32_t len = *(uint32_t*)&((char*)object)[vt->array_len_offset];
        char*  array = ((char*)object) + vt->object_size;
        for (; len-- > 0; array += vt->array_el_size) {
            gc_fsa_mark_sweep$scan_elements((object_t**)array, vt->array_el_pointer_locations, fixup);
        }
    }
}

static NOINLINE_DEBUG bool gc_fsa_mark_sweep$scan_page(gc_page_t *page) {
    mask_bits_t did_some = 0;
    for (unsigned index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index) {
        mask_bits_t seen_bits = page->head.scanner.seen.a[index];
        mask_bits_t scan_bits = seen_bits &~ page->head.scanner.scanned.a[index];
        page->head.scanner.scanned.a[index] = seen_bits; // Mark all 'seen' as 'scanned' now
        did_some |= scan_bits;

        unsigned offset = index * GC_MASK_SIZE;
        while (scan_bits) {
            unsigned slot = __builtin_ctzll(scan_bits);
            scan_bits &= scan_bits - 1; // Clears the lowest bit with value 1
            gc_fsa_mark_sweep$scan_object((object_t*)&page->slots[slot + offset]);
        }
    }
    return did_some != 0;
}

// Drain the mark worklist to EMPTY: pop the top object, scan it (which may
// push more back-edges), repeat until nothing remains. Each object is pushed
// at most once per cycle (only when its seen bit transitions unset->set), so
// total pops are bounded by the live set and this always terminates.
static void gc_fsa_mark_sweep$drain_worklist(void) {
    for (object_t *o; (o = mark_worklist_pop()) != NULL; ) {
        // No scanned-bit write here: the only reader is the page re-diff after
        // a mutator-barrier requeue, where a duplicate scan is idempotent
        // (mark_object skips already-seen children) — cheaper than a
        // page-header RMW per drained object, the dominant population.
        gc_fsa_mark_sweep$scan_object(o);
        if (UNLIKELY(gc_stats_enabled)) gc_prof_drained++;
    }
}

// Multi-consumer reprocess-ring pump. Head is claimed by CAS (an
// unconditional fetch_add could pass `tail` when two pumpers race one entry,
// leaving the loser spinning on an empty slot forever).
static void gc_fsa_mark_sweep$pump_ring(void) {
    for (;;) {
        size_t head = atomic_load(&reprocess_page_head);
        if (head >= atomic_load(&reprocess_page_tail))
            break;
        if (!atomic_compare_exchange_weak(&reprocess_page_head, &head, head + 1))
            continue;
        // The consumed entry is IN FLIGHT until its requeue (or deferral to
        // the claiming owner) lands — the transition tail must not declare
        // the stage done while an entry is between the ring and the lists.
        atomic_fetch_add_explicit(&gc_pages_in_flight, 1, memory_order_acq_rel);
        gc_page_t *page;
        do {page = atomic_exchange(&reprocess_page_list[head % REPROCESS_PAGE_COUNT], NULL);
        } while (page == NULL);
        GC_STAT_BUMP(gc_stat_rq_repro);
        gc_fsa_mark_sweep$page_needs_scan(page);
        atomic_fetch_sub_explicit(&gc_pages_in_flight, 1, memory_order_acq_rel);
    }
}

// The PARALLEL BODY of the mark stage: any number of executors run this
// concurrently. Page claims and links go through the pool lock; everything
// inside a claimed page is owner-exclusive. Returns true when the scan list
// looks empty — a HINT to attempt the (exclusive) transition, never a verdict.
static NOINLINE_DEBUG bool gc_fsa_mark_sweep_body() {
    GC_STAT_BUMP(gc_stat_mark_steps);
    const unsigned step_pages = gc_step_base * gc_pace_credit();
    uint64_t _t0 = gc_stats_enabled ? gc_tsc() : 0;

    // BATCHED claims/publication, same shape as prune (see the comment
    // there): one hold claims up to MARK_CLAIM_BATCH pages, one publishes
    // the batch's requeues and completions.
    enum { MARK_CLAIM_BATCH = 8 };
    unsigned count = 0;
    while (count < step_pages) {
        gc_page_t *batch[MARK_CLAIM_BATCH];
        unsigned want = step_pages - count;
        if (want > MARK_CLAIM_BATCH) want = MARK_CLAIM_BATCH;
        unsigned n = 0;
        // Stage-guarded claim: the pool lock serialises this against the
        // transition tail's verify-and-store, so a pop can never race the
        // stage forward and claim a NEXT-cycle page, and the in_flight
        // increment is visible to any tail that observes the pop.
        gc_pool_lock();
        if (atomic_load_explicit(&stage, memory_order_acquire) == GC_STAGE_MARK_SWEEP) {
            while (n < want) {
                gc_page_t *p = (gc_page_t*)list_pop(&pages_to_scan);
                if (p == NULL) break;
                // Fresh-claim flag clear INSIDE the lock: outside it, a pump's
                // concurrent deferral (also pool-locked) could land between
                // the pop and the clear and be silently clobbered.
                atomic_store(&p->head.scanner.requeue_pending, false);
                batch[n++] = p;
            }
            if (n != 0)
                atomic_fetch_add_explicit(&gc_pages_in_flight, (int)n, memory_order_acq_rel);
        }
        gc_pool_unlock();
        if (n == 0) break;
        count += n;
        list_element_t requeue = {&requeue, &requeue};   // -> pages_to_scan
        list_element_t done    = {&done,    &done};      // -> pages_to_prune
        for (unsigned bi = 0; bi < n; ++bi) {
        gc_page_t *page = batch[bi];
        GC_STAT_BUMP(gc_stat_pages_popped);
        if (page->head.scanner.processed_by_epoch == epoch) {   // instrumented assert
            fprintf(stderr, "[DOUBLE-CLAIM] page=%p epoch=%u links=%p/%p pending=%d cycle=%llu\n",
                    (void*)page, epoch, (void*)page->head.list.next, (void*)page->head.list.prev,
                    (int)atomic_load(&page->head.scanner.requeue_pending),
                    (unsigned long long)atomic_load(&gc_cycle_count));
            fflush(stderr);
            abort();
        }

        GC_PROF_LAP(gc_prof_t_merge, _t0);
        // ENTER on "the merged target has any bits" — a REQUEUED page arrives
        // with its late marks already folded into `seen` (end-of-page re-merge)
        // and an empty atomic source, and its diff must still run. REPEAT on
        // "the merge added NEW bits" — the only loop-safe condition (target
        // bits are monotonic and bounded; looping on target-nonempty spins
        // forever, and on source-nonempty for as long as mutators re-mark).
        if (bitmap_or_test_reset_all(&page->head.scanner.seen, &page->head.scanner.atomic_seen)) {
            do {
                while (gc_fsa_mark_sweep$scan_page(page)) {
                    if (UNLIKELY(gc_stats_enabled)) gc_prof_passes++;
                }
            } while (bitmap_or_test_new_reset_all(&page->head.scanner.seen, &page->head.scanner.atomic_seen));
        }

        page->head.scanner.processed_by_epoch = epoch;
        GC_PROF_LAP(gc_prof_t_pages, _t0);

        // Finish the page: drain its whole back-edge closure now, so it (and
        // everything its scan reached on already-processed pages) is fully
        // resolved before the next pop — the page-pop count then equals the
        // live-page count exactly, which is what the structural pacing's
        // "scan N pages per allocation" promise rests on. processed_by_epoch
        // is set FIRST so a back-edge landing on THIS page during the drain
        // queues and resolves too, rather than setting a seen bit with no
        // scanner to follow it.
        gc_fsa_mark_sweep$drain_worklist();
        GC_PROF_LAP(gc_prof_t_drain, _t0);

        // Catch mutator marks that landed in atomic_seen during this page's
        // own processing — chiefly the window between the merge above and
        // processed_by_epoch being set, where the barrier saw a mismatch and
        // did NOT self-enqueue on the reprocess ring (this is their only catch
        // point); marks after epoch was set are also caught here, redundantly
        // with the ring. Re-queue the page so the merged bits get scanned.
        // The page is linked onward only HERE, after the owner's last touch
        // of its bitmaps — while claimed (on no list) it is invisible to
        // concurrent requeues, so no other executor can claim or splice it.
        bool late_bits = bitmap_or_test_source_reset_all(&page->head.scanner.seen, &page->head.scanner.atomic_seen);
        bool deferred  = atomic_exchange(&page->head.scanner.requeue_pending, false);
        if (late_bits || deferred) {
            GC_STAT_BUMP(gc_stat_rq_drain);
            GC_STAT_BUMP(gc_stat_requeued);
            page->head.scanner.processed_by_epoch = 0;
            list_link(&requeue, (list_element_t*)&page->head.list);
        } else {
            list_link(&done, (list_element_t*)&page->head.list);
        }
        }
        gc_pool_lock();
        list_move(&pages_to_scan,  &requeue);
        list_move(&pages_to_prune, &done);
        gc_pool_unlock();
        // Release in-flight only AFTER publication (see prune).
        atomic_fetch_sub_explicit(&gc_pages_in_flight, (int)n, memory_order_acq_rel);
    }

    // Move re-process pages back on to the scan list
    gc_fsa_mark_sweep$pump_ring();

    // The worklist is always empty here — it is drained per page above — so
    // only the scan list governs whether a transition attempt is worthwhile.
    gc_pool_lock();
    bool maybe_done = list_empty(&pages_to_scan);
    gc_pool_unlock();
    return maybe_done;
}

// The EXCLUSIVE transition tail of the mark stage: runs under fsa_lock with
// zero concurrent executors, re-verifies completion, and either requeues work
// (overflow re-scan) or retires the stage. Returns the stage to store.
static NOINLINE_DEBUG void gc_fsa_mark_sweep_tail() {
    // Late ring entries (and any page they requeue) keep the stage alive.
    gc_fsa_mark_sweep$pump_ring();
    // The decisive check-and-store happens WITH THE POOL LOCK HELD: any
    // executor mid-claim either finished (visible in_flight/list state) or
    // will re-check the stage under this same lock and back off. A non-zero
    // in-flight count means a page (or a pumped ring entry) is still being
    // worked; try again on a later step.
    gc_pool_lock();
    bool busy = !list_empty(&pages_to_scan)
             || atomic_load_explicit(&gc_pages_in_flight, memory_order_acquire) != 0;
    gc_pool_unlock();
    if (busy)
        return;

    // The reprocess ring overflowed at some point: barrier marks were dropped
    // on the floor, so re-queue the whole heap for a conservative re-scan.
    // This is expensive but safe — and the adaptive pacing (GC work scales
    // with live heap) guarantees the re-scan completes faster than the
    // mutator can re-trigger the overflow, so it cannot livelock.
    bool rp_flag = atomic_exchange(&reprocess_overflow_flag, false);
    if (rp_flag) {
        GC_STAT_BUMP(gc_stat_overflows);
        memset(reprocess_page_list, 0, sizeof(reprocess_page_list));
        reprocess_page_head = reprocess_page_tail = 0;
        gc_pool_lock();
        // Epoch bumps BEFORE the pages become poppable: a concurrent body's
        // claim (serialised by this same lock) must never see a freshly
        // re-queued page still carrying processed_by_epoch == epoch.
        epoch = epoch==UINT32_MAX ? 1 : epoch+1;
        list_move(&pages_to_scan, &pages_to_prune);
        gc_pool_unlock();
        return;   // stage stays MARK_SWEEP for the re-scan
    }

    // All done — verify emptiness and retire the stage in ONE pool-locked
    // breath, so no claim can slip between the verdict and the store. (A
    // mutator barrier that loaded `requested==true` before the store below
    // can still land one late ring entry; it is dropped at the next cycle's
    // ring reset and the object's liveness is covered by prune's residue
    // merge. Pre-existing window, unchanged shape.)
    gc_pool_lock();
    if (list_empty(&pages_to_scan)
            && atomic_load_explicit(&gc_pages_in_flight, memory_order_acquire) == 0) {
        gc_write_barrier_requested = false;
        atomic_store_explicit(&stage, GC_STAGE_PRUNE, memory_order_release);
    }
    gc_pool_unlock();
}





// May this page join the old generation? Only if every outgoing reference of
// every live object lands on an OLD page (or this page itself). This CHECKS
// the purity invariant rather than assuming it, because compaction breaks the
// assumption: relocated objects' copies land on fresh YOUNG pages, so a
// referrer that promoted on age alone could hold old->young edges — which
// minors, skipping old pages, would never trace, and prune would free the
// young side. References point down in age, so promotion converges bottom-up:
// referents promote first, referrers follow a cycle later. A page referencing
// any MUTABLE object (never old) is permanently blocked — correct, since its
// targets must stay traced every cycle.
static bool gc_page_refs_are_old(gc_page_t *page) {
    for (unsigned index = 0; index < sizeof(bitmap_t) / sizeof(mask_bits_t); ++index) {
        mask_bits_t bits = page->head.objects.a[index];
        unsigned  offset = index * GC_MASK_SIZE;
        while (bits) {
            unsigned slot = __builtin_ctzll(bits) + offset;
            bits &= bits-1;
            object_t *object = (object_t*)&page->slots[slot];
            // A PINNED object is mid-mutation (a ListBuilder tail whose
            // `next` is still to be written, or a late pin publishing a
            // write-once slot): its fields can acquire YOUNG references
            // after this walk — promoting the page would hide those young
            // targets from every minor cycle and prune would free them while
            // the structure is live (the -O3 self-compile ChainLink dangle).
            // So block promotion while any pin is present; a later prune
            // re-walks and promotes normally. NOTE this check alone is
            // check-then-act: a LATE pin can land on an object this walk has
            // already passed. That window is closed by the Dekker handshake
            // at the promotion site (old-then-recheck-redirty, paired with
            // gc_note_late_write's redirty-then-read-old), not here.
            if (vtable_is_pinned(object->vtable))
                return false;
            // Non-compacted page: the vtable word is a real vtable (mask the
            // pin bit before dereferencing fields).
            vtable_t *vt = vtable_untag(object->vtable);

            GC_FOR_EACH_PTR_WINDOW(vt, object, m, slots)
            while (m) {
                unsigned i = __builtin_ctzll(m); m &= m-1;
                object_t *child = slots[i];
                if (!gc_object_is_on_heap_fast(child)) continue;
                gc_page_t *cp = (gc_page_t*)((uintptr_t)child &~ (uintptr_t)(GC_PAGE_SIZE-1));
                // A reference is acceptable if it points within this page, or
                // to a page that is either fully old or dirty-old. Dirty-old
                // counts: such a page is force-marked as a root on every minor
                // collection, so everything it references is traced no matter
                // who points at it. If we instead demanded the target be fully
                // old, two aged pages that reference each other could never
                // promote — neither can become old before the other already
                // is. (That circular wait once left ~2,200 pages permanently
                // stuck as dirty: a settled dictionary whose tree pages all
                // point at one another.)
                if (cp != page && !cp->head.old && !cp->head.dirty_old) return false;
            }
            if (vt->array_el_pointer_locations) {
                uint32_t len = *(uint32_t*)&((char*)object)[vt->array_len_offset];
                char*  array = ((char*)object) + vt->object_size;
                for (; len-- > 0; array += vt->array_el_size) {
                    ptr_mask_t am = vt->array_el_pointer_locations;
                    while (am) {
                        unsigned i = __builtin_ctzll(am); am &= am-1;
                        object_t *child = ((object_t**)array)[i];
                        if (!gc_object_is_on_heap_fast(child)) continue;
                        gc_page_t *cp = (gc_page_t*)((uintptr_t)child &~ (uintptr_t)(GC_PAGE_SIZE-1));
                        // Same acceptance rule as the object-field branch above.
                        if (cp != page && !cp->head.old && !cp->head.dirty_old) return false;
                    }
                }
            }
        }
    }
    return true;
}

// The PARALLEL BODY of the prune stage: any number of executors run this
// concurrently. A claimed page is owner-exclusive for everything — liveness,
// poison, promotion decisions, COMPACTION (relocation targets go to the
// claiming worker's own bump regions), and freeing. Shared effects reduce to
// pool-locked list surgery and relaxed atomic counter adds. Returns true when
// the prune list looks empty — a hint to attempt the exclusive transition.
static NOINLINE_DEBUG bool gc_fsa_prune_body() {
    GC_STAT_BUMP(gc_stat_prune_steps);
    const unsigned step_pages = gc_prune_base * gc_pace_credit();
    // BATCHED claims and publication: one pool-lock hold claims up to
    // PRUNE_CLAIM_BATCH pages, one more publishes the whole batch's
    // survivors and promotions. Per-page holds made the pool lock the
    // machine-wide bottleneck at T=12 (~47% of ALL cycles waiting on it —
    // perf c2c, 2026-07-08); prune is the heaviest client at ~16x the scan by default
    // claim rate. Batch results collect on LOCAL chains — claimed pages are
    // unlinked and invisible, so no lock is needed until publication, and
    // promotion simplifies: the page joins old_pages directly instead of
    // being published to pages_to_scan and unlinked again.
    enum { PRUNE_CLAIM_BATCH = 16 };
    unsigned count = 0;
    while (count < step_pages) {
        gc_page_t *batch[PRUNE_CLAIM_BATCH];
        unsigned want = step_pages - count;
        if (want > PRUNE_CLAIM_BATCH) want = PRUNE_CLAIM_BATCH;
        unsigned n = 0;
        gc_pool_lock();
        if (atomic_load_explicit(&stage, memory_order_acquire) == GC_STAGE_PRUNE) {
            while (n < want) {
                gc_page_t *p = (gc_page_t*)list_pop(&pages_to_prune);
                if (p == NULL) break;
                // Flag clear INSIDE the claim lock (see mark body).
                atomic_store(&p->head.scanner.requeue_pending, false);
                batch[n++] = p;
            }
            if (n != 0)
                atomic_fetch_add_explicit(&gc_pages_in_flight, (int)n, memory_order_acq_rel);
        }
        gc_pool_unlock();
        if (n == 0) break;
        count += n;
        list_element_t survivors = {&survivors, &survivors};   // -> pages_to_scan
        list_element_t promoted  = {&promoted,  &promoted};    // -> old_pages
        size_t batch_survivor_pages = 0, batch_survivor_slots = 0, batch_promoted = 0;
        for (unsigned bi = 0; bi < n; ++bi) {
        gc_page_t *page = batch[bi];
        assert(page->head.scanner.processed_by_epoch == epoch);
        // (flag cleared under the claim lock above)   // stale by now:
        // during PRUNE the barrier is off and mark executors are gone, so a
        // lingering flag can only be a consumed mark-stage duplicate whose
        // bits the residue merge below already covers.

        // Merge any residual atomic_seen bits into the liveness record before
        // reading it. By prune time these can only be DRAINED BACK-EDGES:
        // mark_object records a back-edge in atomic_seen and direct-scans it
        // via the worklist (children fully traced), but nothing merges the bit
        // once the page has been processed — without this merge, prune would
        // free an object the drain proved live. Everything else is excluded:
        // mutator marks in the pre-processed window are absorbed by the
        // end-of-page re-merge, later mutator marks ring-enqueue the page for
        // a genuine re-scan, and a barrier straddling the mark stage's retire
        // is drained by the three-state handshake (see gc_barrier_enter) —
        // after a successful retire no mutator mark can land at all.
        bitmap_or_test_source_reset_all(&page->head.scanner.seen,
                                        &page->head.scanner.atomic_seen);

        if (bitmap_test_all(&page->head.scanner.seen)) {
            if (UNLIKELY(gc_stats_enabled))
                gc_occupancy_account(page);
            // Debug (YAFL_GC_POISON): wipe each reclaimed object with 0x42 so
            // any surviving reference to it fails loudly instead of silently
            // reading stale data. Paired with the poison check in scan_object.
            //
            // Sizes come from the objects bitmap alone — bump allocation packs
            // objects contiguously, so an object extends from its start bit to
            // the next start bit (or the end of the page). Never read vtables
            // here: a dead slot can be a forwarder left by compaction, and
            // following its chain can land on a target poisoned moments ago.
            if (UNLIKELY(gc_poison_enabled)) {
                unsigned prev_slot = 0;
                bool     prev_dead = false;
                for (unsigned index = 0; index < sizeof(bitmap_t) / sizeof(mask_bits_t); ++index) {
                    mask_bits_t starts = page->head.objects.a[index];
                    unsigned    offset = index * GC_MASK_SIZE;
                    while (starts) {
                        unsigned slot = __builtin_ctzll(starts) + offset;
                        starts &= starts-1;
                        if (prev_dead) {
                            LOG(ULTRA, "RELEASE(0x%lx)", (uintptr_t)&page->slots[prev_slot]);
                            memset(&page->slots[prev_slot], 0x42,
                                   (size_t)(slot - prev_slot) * sizeof(slot_t));
                        }
                        prev_slot = slot;
                        prev_dead = !bitmap_test(&page->head.scanner.seen, slot);
                    }
                }
                if (prev_dead) {
                    LOG(ULTRA, "RELEASE(0x%lx)", (uintptr_t)&page->slots[prev_slot]);
                    memset(&page->slots[prev_slot], 0x42,
                           (size_t)(SLOTS_PER_PAGE - prev_slot) * sizeof(slot_t));
                }
            }
            // Stability: did every object that entered this prune leave it
            // alive? Drives promotion below — sampled BEFORE the bitmap is
            // overwritten with the survivors.
            uint64_t _tp0 = gc_stats_enabled ? gc_tsc() : 0;
            bool page_stable = memcmp(&page->head.objects, &page->head.scanner.seen,
                                      sizeof(bitmap_t)) == 0;
            batch_survivor_pages += page->head.pages;
            // Byte-honest live count for the dwell threshold — sampled before
            // the bitmap overwrite (like the survey), but only ADDED below,
            // after the promotion decision: pages that leave the young
            // rotation (old or dirty) must not count as young survivors, and
            // that includes pages a major demoted and this same prune
            // re-promoted — counting those once per major ballooned the
            // threshold right back to the cap.
            size_t page_live_slots = page->head.pages > 1
                ? (size_t)page->head.pages * SLOTS_PER_PAGE
                : gc_page_live_slots(page);
            GC_PROF_LAP(gc_prof_t_live, _tp0);
            page->head.objects = page->head.scanner.seen;
            bitmap_reset_all(&page->head.scanner.seen);
            bitmap_reset_all(&page->head.scanner.scanned);
            bitmap_reset_all(&page->head.scanner.atomic_seen);
            list_link(&survivors, (list_element_t*)&page->head.list);
#if COMPACT_THRESHOLD_PERCENT > 0
            gc_compact_page(page);
#endif
            // Cleared for the next cycle: root scanning re-pins if a conservative
            // reference still points into this page.
            page->head.scanner.pinned = false;

            // Promotion: an immutable single page that keeps surviving leaves
            // the rotation for the old generation. Compacted pages never
            // promote — their forwarders point at YOUNG copies, which the
            // old-skip would lose. Checked after gc_compact_page so a page
            // compacted THIS cycle is excluded.
            //
            // Two-stage: if every outgoing reference already lands on an old
            // page, the page becomes fully exempt (`old`). Otherwise it
            // becomes DIRTY-old: still in the rotation, force-marked as a
            // root each cycle (so its young targets stay traced — sound by
            // construction), and re-checked here every prune until its
            // targets have promoted too. Because the whole aged cohort
            // promotes in one wave, the dirty set usually empties a cycle
            // later — without this, full exemption would crawl one page-graph
            // layer per cycle and never catch up on deep structures.
            // Ageing requires STABILITY across allocation VOLUME, not cycle
            // counts: a page promotes once it has stayed death-free across
            // two dwell windows' worth of allocation (the young heap turning
            // over twice). Any death resets the clock; the first prune only
            // STARTS it (birth protection makes that prune force-stable, so
            // it proves nothing). A cycle-count criterion promoted mid-life
            // churn wholesale whenever cycles were short, and every
            // allocation-frontier page when they were long — in both cases
            // the dirty-old force-mark then froze the promoted pages' dead
            // slots until a major (observed: ~190 MiB accreted on yspell).
            // After a major's honest trace reveals deaths, the reset makes
            // the demoted page re-earn the full volume before re-freezing.
            if (gc_gen_enabled
                    && !page->head.mutable && !page->head.compacted && page->head.pages == 1) {
                uint64_t clock = atomic_load_explicit(&gc_alloc_clock, memory_order_relaxed);
                if (!page_stable || page->head.stable_since == UINT64_MAX) {
                    if (UNLIKELY(gc_stats_enabled)) gc_prof_block_unstable++;
                    page->head.stable_since = clock;
                    page->head.refs_defer = page->head.refs_backoff = 0;
                }
                if (gc_promote_volume != 0
                        && page->head.stable_since != clock
                        && clock - page->head.stable_since >= gc_promote_volume) {
                    // The refs walk is a full object walk of the page; a page
                    // that just failed it rarely passes the very next prune
                    // (its targets graduate in waves, and a page referencing
                    // anything mutable NEVER passes), so failures back off
                    // exponentially. Deferred prunes are sound: the page
                    // stays dirty-old, a force-marked root.
                    if (page->head.refs_defer > 0) {
                        page->head.refs_defer -= 1;
                        if (UNLIKELY(gc_stats_enabled)) gc_prof_defer++;
                    } else if (gc_page_refs_are_old(page)) {
#ifdef YAFL_GC_RACE_PROBE
                        // Test-only hook (tests/test_gc_late_pin_race.c),
                        // compiled into that target alone: called between
                        // the refs walk and the old-claim, the check-then-act
                        // window the handshake below closes, so the test can
                        // land a late write inside it deterministically.
                        { extern void gc_test_race_probe(gc_page_t*);
                          gc_test_race_probe(page); }
#endif
                        // Claim `old` FIRST, then re-check for a late write
                        // that raced the walk. This is the promoter's half of
                        // the Dekker handshake with gc_note_late_write: each
                        // side writes its flag, fences, then reads the
                        // other's. The refs walk alone is check-then-act — a
                        // late pin can land on an object the walk already
                        // passed, its note read `old` as still false, and the
                        // page would promote holding a young edge nothing
                        // traces. With the handshake, either the writer sees
                        // `old` set (and flags the global for next cycle's
                        // demotion) or the exchange below sees the writer's
                        // flag — dropping to dirty_old, which is force-marked
                        // and therefore always safe.
                        page->head.old = true;
                        atomic_thread_fence(memory_order_seq_cst);
                        if (atomic_exchange_explicit(&page->head.redirty, false,
                                                     memory_order_relaxed)) {
                            // A late write raced us (or landed while young and
                            // left its flag). Not a refusal, a deferral: no
                            // backoff bump, the next prune re-walks and
                            // promotes an untouched page normally.
                            page->head.old = false;
                            page->head.dirty_old = true;
                            if (UNLIKELY(gc_stats_enabled)) gc_prof_promote_dirty++;
                        } else {
                            if (UNLIKELY(gc_stats_enabled)) gc_prof_promote_ok++;
                            page->head.dirty_old = false;
                            // Belt-and-braces: the only road back into the
                            // rotation (major demotion) resets these anyway.
                            page->head.refs_defer = page->head.refs_backoff = 0;
                            // No lock: the page sits on this batch's LOCAL
                            // survivors chain — move it to the local promoted
                            // chain; publication happens once, below.
                            list_unlink((list_element_t*)&page->head.list);
                            list_link(&promoted, (list_element_t*)&page->head.list);
                            batch_promoted += 1;
                        }
                    } else {
                        if (UNLIKELY(gc_stats_enabled)) gc_prof_promote_dirty++;
                        page->head.dirty_old = true;
                        uint8_t b = page->head.refs_backoff;
                        b = b == 0 ? 1
                            : b < GC_REFS_BACKOFF_CAP ? (uint8_t)(b * 2)
                            : GC_REFS_BACKOFF_CAP;
                        page->head.refs_backoff = b;
                        page->head.refs_defer = b;
                    }
                } else if (UNLIKELY(gc_stats_enabled) && page->head.stable_since != clock) {
                    gc_prof_block_volume++;
                }
            } else if (UNLIKELY(gc_stats_enabled)) {
                gc_prof_block_kind++;
            }
            // Young survivor accounting (see comment above the sample site).
            if (!page->head.old && !page->head.dirty_old)
                batch_survivor_slots += page_live_slots;
            if (UNLIKELY(gc_stats_enabled)) gc_prof_t_prune_rest += gc_tsc() - _tp0;
        } else {
            // Residue merged above, so an all-dead page truly has no marks.
            assert(bitmap_test_all(&page->head.scanner.atomic_seen) == false);
            gc_page_free(page);
        }
        }
        gc_pool_lock();
        list_move(&pages_to_scan, &survivors);
        list_move(&old_pages, &promoted);
        gc_pool_unlock();
        gc_cycle_survivors      += batch_survivor_pages;
        gc_cycle_survivor_slots += batch_survivor_slots;
        gc_old_page_count       += batch_promoted;
        // Release in-flight only AFTER publication: a transition that sees
        // zero in-flight must also see every batch page on its final list.
        atomic_fetch_sub_explicit(&gc_pages_in_flight, (int)n, memory_order_acq_rel);
    }

    gc_pool_lock();
    bool maybe_done = list_empty(&pages_to_prune);
    gc_pool_unlock();
    return maybe_done;
}

// The EXCLUSIVE transition tail of the prune stage: runs under fsa_lock with
// zero concurrent executors. Re-verifies the pool is drained, then runs the
// cycle epilogue (promotion volume, scavenge, baselines) and retires to IDLE.
static NOINLINE_DEBUG void gc_fsa_prune_tail() {
    gc_pool_lock();
    bool done = list_empty(&pages_to_prune)
             && atomic_load_explicit(&gc_pages_in_flight, memory_order_acquire) == 0;
    gc_pool_unlock();
    if (done) {
        // Promotion volume for the next cycle: a page must stay stable across
        // this many pages of allocation before it ages into the old
        // generation — eight turnovers of the young live set (byte-honest:
        // page counts over-state ~2x when live and dead interleave on pages),
        // floored at 1/64th of the heap for tiny young sets. Deliberately
        // conservative: with continuous cycles a churn page sees many prunes,
        // and anything promoted too early has its garbage frozen by the
        // dirty-old force-mark until a major.
        size_t young = gc_cycle_survivor_slots / SLOTS_PER_PAGE;
        size_t floor_ = memory_total_pages() / 64;
        size_t volume = young * 8;
        gc_promote_volume = volume > floor_ ? volume : floor_;

        // Hand back the pages that went this whole cycle without any thread
        // wanting them, and rotate the pool's generations. This is the
        // measured surplus; it needs no retain target because it is not
        // guessing at how much slack to keep — it is reporting how much went
        // unused. Runs as the last thing in the exclusive prune tail, where
        // the transient HEAD marker it uses stays invisible to the
        // conservative scanner.
        memory_pool_release_cycle();

        // The age-based scavenger still covers what the pool does not: freed
        // RUNS, and singles claimed by the fallback scan rather than the pool.
        // Its retain target is the term the release rule is meant to retire —
        // measured simultaneously 3x too large on test_gc_pressure and too
        // small here — so it stays only until the pool's numbers show the
        // remainder is not worth a second mechanism.
        size_t slack = young * 3;
        if (UNLIKELY(yafl_prof_enabled))
            yafl_prof_runtime_push(YAFL_PROF_RES_SCAVENGE);
        memory_scavenge(slack > GC_SCAVENGE_RETAIN_FLOOR ? slack : GC_SCAVENGE_RETAIN_FLOOR,
                        GC_SCAVENGE_BUDGET);
        if (UNLIKELY(yafl_prof_enabled))
            yafl_prof_runtime_pop();

        if (UNLIKELY(yafl_heapprof_enabled))
            yafl_heapprof_cycle_end(memory_count() * (size_t)GC_PAGE_SIZE,
                                    memory_total_pages() * (size_t)GC_PAGE_SIZE);
        if (UNLIKELY(gc_stats_enabled))
            fprintf(stderr, "[GC CYCLE] survivors=%zu dirty=%zu old=%zu young=%zu promote_vol=%zu in_use=%zu cons_seeds=%llu (pages)\n",
                    gc_cycle_survivors, gc_dirty_old_count, gc_old_page_count,
                    young, gc_promote_volume, memory_count(),
                    (unsigned long long)atomic_load(&gc_stat_cons_seeds));

        if (UNLIKELY(gc_stats_enabled)) {
            // Snapshot this cycle's page-occupancy survey for the exit report.
            memcpy(gc_snap_pages, gc_occ_pages, sizeof gc_occ_pages);
            memcpy(gc_snap_live,  gc_occ_live,  sizeof gc_occ_live);
            memcpy(gc_snap_sparse, gc_occ_sparse, sizeof gc_occ_sparse);
            memcpy(gc_snap_sparse_free, gc_occ_sparse_free, sizeof gc_occ_sparse_free);
            gc_snap_large = gc_occ_large;
            gc_snap_sparse_fwd = gc_occ_sparse_fwd;
            gc_snap_sparse_pin = gc_occ_sparse_pin;
            gc_snap_sparse_oth = gc_occ_sparse_oth;
        }

        // End of a full GC cycle. After a major, the re-promotions above have
        // rebuilt the old generation — record its size (clean AND dirty: the
        // bulk re-promotes through the dirty stage) as the doubling baseline.
        if (gc_major_cycle) {
            gc_old_baseline = gc_old_page_count + gc_dirty_old_count;
            gc_major_cycle  = false;
            GC_STAT_BUMP(gc_stat_majors);
        }
        atomic_fetch_add(&gc_cycle_count, 1);
        // Retire under the pool lock: no prune claim can interleave between
        // the (re-verified) empty pool and the stage store.
        gc_pool_lock();
        if (list_empty(&pages_to_prune)
                && atomic_load_explicit(&gc_pages_in_flight, memory_order_acquire) == 0)
            atomic_store_explicit(&stage, GC_STAGE_IDLE, memory_order_release);
        gc_pool_unlock();
    }
}






static alignas(CACHE_LINE_SIZE) atomic_bool fsa_lock;

// Attempt the exclusive stage transition after a parallel body reported "no
// work left". Sound only when NO executor is mid-page: an in-flight executor
// can still requeue pages (end-of-page re-merge) or push ring entries, so the
// tail runs only at executors==0, under fsa_lock, and re-verifies emptiness
// itself. Losing the lock is fine — whoever holds it will attempt the same
// transition, and if the stage moves on nobody re-enters the old body.
static void gc_fsa_try_transition(enum gc_stage from) {
    bool expected = false;
    if (!atomic_compare_exchange_strong(&fsa_lock, &expected, true))
        return;
    if (atomic_load_explicit(&stage, memory_order_acquire) == from) {
        if (from == GC_STAGE_MARK_SWEEP)
            gc_fsa_mark_sweep_tail();
        else
            gc_fsa_prune_tail();
    }
    atomic_store(&fsa_lock, false);
}

static thread_local bool gc_in_fsa = false;

static NOINLINE_DEBUG bool gc_fsa_impl() {
    assert(gc_thread_info.thread_state == THREAD_STATE_RUNNING);

    // RE-ENTRANCY GUARD: collector work can allocate (compaction's relocation
    // targets refill bump regions, which drives pacing), and that inner
    // gc_page_alloc calls back into gc_fsa. Under the serial design the
    // fsa_lock CAS failed against its own holder — accidental but load-
    // bearing re-entrancy protection. The parallel stages take no lock, so
    // the guard must be explicit: a thread already inside the collector never
    // becomes a nested executor (which would clobber in_relocation, stall
    // relocation allocs in the reserve loop, and wedge with pages in flight).
    if (gc_in_fsa)
        return false;
    gc_in_fsa = true;

    // PARALLEL stages: MARK_SWEEP and PRUNE take no lock — every caller
    // becomes an executor and claims pages concurrently. The executor count
    // brackets the body so transitions can wait for mid-page work; the stage
    // recheck after incrementing closes the load->increment race (a raced
    // entry just backs out and the caller retries via its lag credit).
    enum gc_stage st = atomic_load_explicit(&stage, memory_order_acquire);
    if (st == GC_STAGE_MARK_SWEEP || st == GC_STAGE_PRUNE) {
        atomic_fetch_add_explicit(&gc_stage_executors, 1, memory_order_acq_rel);
        if (atomic_load_explicit(&stage, memory_order_acquire) != st) {
            atomic_fetch_sub_explicit(&gc_stage_executors, 1, memory_order_acq_rel);
            gc_in_fsa = false;
            return false;
        }
        struct timespec t_par_in;
        if (gc_stats_enabled) clock_gettime(CLOCK_MONOTONIC, &t_par_in);
        LOG(TRACE, st == GC_STAGE_MARK_SWEEP ? "GC_STAGE_MARK_SWEEP" : "GC_STAGE_PRUNE");
        bool maybe_done = (st == GC_STAGE_MARK_SWEEP)
            ? gc_fsa_mark_sweep_body()
            : gc_fsa_prune_body();
        if (gc_stats_enabled) {
            struct timespec t_par_out;
            clock_gettime(CLOCK_MONOTONIC, &t_par_out);
            uint64_t ns = (uint64_t)((t_par_out.tv_sec - t_par_in.tv_sec) * 1000000000LL
                                   + (t_par_out.tv_nsec - t_par_in.tv_nsec));
            atomic_fetch_add_explicit(&gc_stat_stage_ns[st], ns, memory_order_relaxed);
            atomic_fetch_add_explicit(&gc_stat_fsa_calls, 1, memory_order_relaxed);
            enum { LOG2_BASE_P = 8 * sizeof(uint64_t) - 1 };
            unsigned bucket = ns < 2 ? 0 : LOG2_BASE_P - (unsigned)__builtin_clzll(ns);
            if (bucket >= GC_LAT_BUCKETS) bucket = GC_LAT_BUCKETS - 1;
            atomic_fetch_add_explicit(&gc_stat_lat[st][bucket], 1, memory_order_relaxed);
        }
        atomic_fetch_sub_explicit(&gc_stage_executors, 1, memory_order_acq_rel);
        if (maybe_done)
            gc_fsa_try_transition(st);
        gc_in_fsa = false;
        return true;
    }

    // EXCLUSIVE stages: the original single-executor path.
    bool expected = false;
    if (!atomic_compare_exchange_strong(&fsa_lock, &expected, true)) {
        gc_in_fsa = false;
        return false;
    }

    struct timespec t_in;
    enum gc_stage entry_stage = atomic_load_explicit(&stage, memory_order_acquire);
    if (gc_stats_enabled) clock_gettime(CLOCK_MONOTONIC, &t_in);

    switch (entry_stage) {
        case GC_STAGE_NOT_STARTED:
            break;

        case GC_STAGE_IDLE:
            // No dwell: the system is in a permanent GC cycle, so IDLE is
            // just the boundary between one cycle and the next — the next
            // allocation-driven step starts the new cycle immediately. The
            // state exists (rather than chaining PRUNE -> START directly)
            // so stepped tests can detect cycle boundaries.
            LOG(TRACE, "GC_STAGE_IDLE");
            atomic_store_explicit(&stage, GC_STAGE_START, memory_order_release);
            break;

        case GC_STAGE_START:
            LOG(TRACE, "GC_STAGE_START");
            atomic_store_explicit(&stage, gc_fsa_start(), memory_order_release);
            break;

        case GC_STAGE_SCAN_ROOTS:
            LOG(TRACE, "GC_STAGE_SCAN_ROOTS");
            atomic_store_explicit(&stage, gc_fsa_scan_roots(), memory_order_release);
            break;

        case GC_STAGE_MARK_SWEEP:
        case GC_STAGE_PRUNE:
            // Raced: the stage moved into a parallel stage between our load
            // and the lock. Nothing to do here — the caller re-enters and
            // takes the parallel route.
            break;

        default:
            abort();
    }

    if (gc_stats_enabled) {
        struct timespec t_out;
        clock_gettime(CLOCK_MONOTONIC, &t_out);
        // Compute the whole delta in SIGNED arithmetic, then cast once: the
        // nanosecond term goes negative across a second boundary and the
        // seconds term cancels it. Casting that term to unsigned first would
        // wrap it instead of cancelling. CLOCK_MONOTONIC makes the total
        // non-negative.
        uint64_t ns = (uint64_t)((t_out.tv_sec - t_in.tv_sec) * 1000000000LL
                               + (t_out.tv_nsec - t_in.tv_nsec));
        atomic_fetch_add_explicit(&gc_stat_stage_ns[entry_stage], ns, memory_order_relaxed);
        atomic_fetch_add_explicit(&gc_stat_fsa_calls, 1, memory_order_relaxed);
        // Per-call latency histogram (log2 ns buckets): the uniformity of a
        // gc_fsa call's cost is a design goal — every call should retire a
        // similar-sized quantum of work. Printed as [GC LAT] at exit.
        // floor(log2 ns) = (bit width − 1) − leading zeros; ns is uint64_t,
        // and the _Static_assert above pins clzll's operand to that width.
        enum { LOG2_BASE = 8 * sizeof(uint64_t) - 1 };
        unsigned bucket = ns < 2 ? 0 : LOG2_BASE - (unsigned)__builtin_clzll(ns);
        if (bucket >= GC_LAT_BUCKETS) bucket = GC_LAT_BUCKETS - 1;
        atomic_fetch_add_explicit(&gc_stat_lat[entry_stage][bucket], 1, memory_order_relaxed);
    }

    atomic_store(&fsa_lock, false);
    gc_in_fsa = false;
    return true;
}

// Profiling shim: bracket ALL collector work with the (GC) pseudo-frame so
// sampled GC time is a named row instead of a smear over whichever function's
// allocation paced the cycle. One pair here beats edits at the four return
// sites of the impl. A nested call (compaction refill re-entering via
// gc_page_alloc) pushes a second (GC) frame around the impl's immediate
// re-entrancy bail-out — harmless and vanishingly rarely sampled.
static bool gc_fsa() {
    if (LIKELY(!yafl_prof_enabled))
        return gc_fsa_impl();
    yafl_prof_runtime_push(YAFL_PROF_RES_GC);
    bool result = gc_fsa_impl();
    yafl_prof_runtime_pop();
    return result;
}


// DEBUG: drive the GC FSA one stage at a time, and read its state, so a test can
// reproduce an exact interleaving deterministically.
EXPORT int  gc_debug_stage(void) { return (int)stage; }
EXPORT void gc_debug_step(void)  { gc_fsa(); }

// DEBUG: force the next cycle to be a major (collect the old generation).
EXPORT void gc_debug_request_major(void) { gc_major_request = true; }

// DEBUG: which generation holds this object? 0 = young, 1 = old,
// -1 = not a managed-heap object.
EXPORT int gc_debug_object_generation(object_t* o) {
    uintptr_t a = (uintptr_t)o;
    if (!o || (a & PTR_TAG_MASK) || (a & (GC_SLOT_SIZE - 1))) return -1;
    gc_page_t* pg = (gc_page_t*)(a & ~(uintptr_t)(GC_PAGE_SIZE - 1));
    if (!memory_pages_is_alloc_head(pg) || pg->head.tag != PAGE_MAGIC_NUMBER) return -1;
    return pg->head.old ? 1 : 0;
}

// DEBUG: classify a heap pointer: 0 = not a managed-heap object slot,
// 1 = live (present in its page's objects bitmap), 2 = reclaimed (slot exists
// but no longer in objects — i.e. pruned this/last cycle).
EXPORT int gc_debug_object_state(object_t* o) {
    uintptr_t a = (uintptr_t)o;
    if (!o || (a & PTR_TAG_MASK) || (a & (GC_SLOT_SIZE - 1))) return 0;
    gc_page_t* pg = (gc_page_t*)(a & ~(uintptr_t)(GC_PAGE_SIZE - 1));
    if (!memory_pages_is_alloc_head(pg) || pg->head.tag != PAGE_MAGIC_NUMBER) return 0;
    if ((a & (GC_PAGE_SIZE - 1)) < offsetof(gc_page_t, slots)) return 0;
    ptrdiff_t slot = (slot_t*)o - pg->slots;
    if (slot < 0 || slot >= SLOTS_PER_PAGE) return 0;
    return bitmap_test(&pg->head.objects, slot) ? 1 : 2;
}

EXPORT void _gc_safe_point2() {
    uint_fast32_t sp = gc_alloc_tl.safe_point_request;
    if (sp & (GC_SAFE_POINT_SCAN_ROOTS|GC_SAFE_POINT_CATCH_UP)) {
        if (gc_fsa() && gc_thread_info.lag_counter > 0) {
            gc_thread_info.lag_counter -= 1;
        } else {
            atomic_fetch_and(&gc_alloc_tl.safe_point_request, ~GC_SAFE_POINT_CATCH_UP);
        }
    }
}


// The mutable-root contract's slow halves (see yafl.h). Field-based so a
// stale pointer to a relocated object follows (and snaps) the forwarding
// chain, exactly like the root scan's own marking.
EXPORT void _gc_root_overwrite2(object_t** slot) {
    atomic_gc_object_seen_by_field(slot);
}

EXPORT void _gc_root_publish2(object_t* value) {
    // Value position — follow forwarding without a slot to snap.
    while (gc_object_is_on_heap_fast(value)) {
        atomic_gc_object_mark_as_seen(value);
        if (LIKELY(!vtable_is_forward(value->vtable))) break;
        value = (object_t*)value->vtable;
    }
}

EXPORT void _gc_mark_as_seen2(object_t *object) {
    if (gc_object_is_on_heap_fast(object)) {
        LOG(ULTRA, "MARK_AS_SEEN(0x%lx) -> %s", (uintptr_t)object, object_get_vtable(object)->name);
        atomic_gc_object_mark_as_seen(object);
    }
}


EXPORT void _gc_write_barrier2(object_t **field, ptr_mask_t mask) {
    while (mask) {
        unsigned index = __builtin_ctzll(mask);
        mask &= mask-1;
        // Follow (and rewrite past) any forwarding pointer left by compaction,
        // so the barrier marks the live copy and the stale reference is replaced
        // rather than re-marked on a subsequent overwrite.
        atomic_gc_object_seen_by_field(&field[index]);
    }
}


EXPORT void gc_start() {
    assert(stage == GC_STAGE_NOT_STARTED);
    gc_read_config();
    yafl_heapprof_init();
    if (gc_stats_enabled) {
        clock_gettime(CLOCK_MONOTONIC, &gc_stats_t0);
        atexit(gc_stats_report);
    }
    stage = GC_STAGE_IDLE;
}

EXPORT void object_gc_init() {
}


// Process-wide CLI args. Set once at startup by the emitted `main()` shim
// (see compiler/codegen/gen.py) before `thread_start(__entrypoint__)`.
EXPORT int     _yafl_argc = 0;
EXPORT char**  _yafl_argv = NULL;

EXPORT object_t* sys_argc(object_t* self) {
    (void)self;
    return integer_from_int32(_yafl_argc);
}

EXPORT object_t* sys_argv_at(object_t* self, object_t* o_index) {
    (void)self;
    int overflow = 0;
    int32_t idx = int32_from_integer_with_overflow(o_index, &overflow);
    if (overflow || idx < 0 || idx >= _yafl_argc) __abort_on_overflow();
    const char* s = _yafl_argv[idx];
    return string_from_bytes((uint8_t*)s, (int32_t)strlen(s));
}




