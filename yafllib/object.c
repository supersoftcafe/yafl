
#define OBJECT_HEADER_EXCLUSIONS

#include "yafl.h"
#include <malloc.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include <time.h>


#define COMPACT_THRESHOLD_PERCENT   33
#define REPROCESS_PAGE_COUNT        16

// --- GC pacing --------------------------------------------------------------
//
// The collector runs CONTINUOUSLY: there is no idle dwell between cycles —
// PRUNE hands straight back to START on the next allocation. The rate of
// collection is linked directly to the rate of allocation, and the pacing is
// stated in PAGES, and nothing else: per page allocated,
//
//     scan  GC_PACE_SCAN_PAGES  (r) pages, and
//     prune GC_PACE_PRUNE_RATIO x r (pruning is that much cheaper per page).
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
// YAFL_GC_STEP_PAGES overrides the scan ratio (prune stays 16x it): larger =
// more GC work per allocation = tighter heap, higher GC share of CPU.
#define GC_PACE_SCAN_PAGES  4     // pages scanned per page allocated — THE knob.
                                  // Peak heap ≈ live x (r+1)/(r-1): r=2 is 3x
                                  // live (measured), r=4 is 1.67x with most of
                                  // the GC-CPU win kept; tune via env per
                                  // deployment.
#define GC_PACE_PRUNE_RATIO 16    // prune pages per scan page (prune is cheap)
#define GC_PACE_CREDIT_MAX  16    // max allocation-pages consumed per gc_fsa
                                  // call; a backlog (multi-page allocation,
                                  // credit accrued across the roots phase)
                                  // drains over a few calls instead of
                                  // spiking one
#define GC_PACE_LAG_MAX     4096  // cap on a thread's accumulated catch-up debt
static unsigned gc_step_base = GC_PACE_SCAN_PAGES;

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
static bool gc_poison_enabled = false;
static bool gc_stats_enabled  = false;
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
    gc_poison_enabled = (e = getenv("YAFL_GC_POISON")) && e[0] && e[0] != '0';
    gc_stats_enabled  = getenv("YAFL_GC_STATS") != NULL;
    gc_gen_enabled    = !((e = getenv("YAFL_GC_GEN")) && e[0] == '0');
}


#ifndef NDEBUG
#define NOINLINE_DEBUG NOINLINE
#else
#define NOINLINE_DEBUG
#endif


enum {
    GC_SAFE_POINT_SCAN_ROOTS = 0x001,
    GC_SAFE_POINT_CATCH_UP   = 0x002
};

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




typedef uintptr_t mask_bits_t;
enum { GC_MASK_SIZE = sizeof(mask_bits_t) * 8 /* bits */ };
enum { GC_SLOT_SIZE = 32 /* bytes */ };

typedef struct {
    mask_bits_t a[GC_PAGE_SIZE / GC_SLOT_SIZE / 8 / sizeof(mask_bits_t)];
} __attribute__((aligned(GC_PAGE_SIZE / GC_SLOT_SIZE / 8))) bitmap_t;

typedef struct slot_t {
    vtable_t *vt;
    struct slot_t *o1, *o2;
    uintptr_t a[(GC_SLOT_SIZE - sizeof(void*)*3) / sizeof(uintptr_t)];
} __attribute__((aligned(GC_SLOT_SIZE))) slot_t;

typedef struct list_element {
    struct list_element *next;
    struct list_element *prev;
} list_element_t;

typedef struct page_head {
    struct {
        struct gc_page *next;
        struct gc_page *prev;
    } list; // Page belongs to a cicular list, somewhere

    struct {
        bitmap_t        seen; // Starting slot of each seen object
        bitmap_t     scanned; // Starting slot of each scanned object
        bitmap_t atomic_seen; // Strictly for the early stage atomic updates
        _Atomic(uint32_t) processed_by_epoch; // Scanned has processed this page..  Reset to false when something changes
        bool          pinned; // Stack references found, which can't be re-written easily
    } scanner;

    bitmap_t objects; // Starting slot of each known object
    uint32_t     tag; // Safety check
    uint32_t   pages; // Number of pages, including this one, in the complete allocation
    bool     mutable; // Contains mutable objects.
    bool   compacted; // Don't compact again.
    bool         old; // Promoted to the old generation: exempt from minor cycles.
    bool   dirty_old; // Aged page still holding young references: exempt from
                      // pruning, but force-marked as a root every cycle until
                      // its targets promote (then it graduates to `old`).
    uint8_t refs_defer;   // prunes left before re-walking gc_page_refs_are_old
    uint8_t refs_backoff; // last defer length; doubles per failed walk up to
                          // GC_REFS_BACKOFF_CAP, so permanently-blocked pages
                          // stop costing a full object walk every prune.
                          // Reset on instability and on major demotion. Sound
                          // while deferred: the page stays dirty-old, i.e. a
                          // force-marked root.
    uint64_t stable_since; // Allocation-clock reading (pages) at the last
                           // prune that found a death on this page — or
                           // UINT64_MAX before the first prune (a page's
                           // first prune is force-stable via birth
                           // protection, so it only STARTS the clock).
                           // Drives volume-based promotion.

} __attribute__((aligned(GC_SLOT_SIZE))) page_head_t;

static const uint32_t PAGE_MAGIC_NUMBER = 0x71ea05c3;
enum { SLOTS_PER_PAGE = (GC_PAGE_SIZE - sizeof(page_head_t)) / sizeof(slot_t) };

typedef struct gc_page {
    page_head_t head;
    slot_t     slots[SLOTS_PER_PAGE];
} __attribute__((aligned(GC_SLOT_SIZE))) gc_page_t;

static_assert(sizeof(gc_page_t) == GC_PAGE_SIZE, "Page size doesn't add up");

static_assert(sizeof(slot_t) == GC_SLOT_SIZE, "Slot size doesn't add up");

enum { MAX_OBJECT_SIZE = sizeof(gc_page_t) - offsetof(gc_page_t, slots[0]) };



static __attribute__((unused)) unsigned bitmap_count(const bitmap_t *bitmap) {
    unsigned count = 0;
    for (unsigned index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index)
        count += __builtin_popcountll(bitmap->a[index]);
    return count;
}

static bool bitmap_fetch_set(bitmap_t *bitmap, unsigned bit) {
    mask_bits_t mask = ((mask_bits_t)1) << (bit % GC_MASK_SIZE);
    mask_bits_t *ptr = &bitmap->a[bit / GC_MASK_SIZE];
    mask_bits_t bits = *ptr;
    *ptr = bits | mask;
    return (bits & mask) != 0;
}

static bool atomic_bitmap_fetch_set(bitmap_t *bitmap, unsigned bit) {
    mask_bits_t mask = ((mask_bits_t)1) << (bit % GC_MASK_SIZE);
    _Atomic(mask_bits_t) *ptr = (_Atomic(mask_bits_t)*)&bitmap->a[bit / GC_MASK_SIZE];
    mask_bits_t bits = atomic_fetch_or(ptr, mask);
    return (bits & mask) != 0;
}

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


enum gc_stage {
    GC_STAGE_NOT_STARTED,
    GC_STAGE_IDLE,       // Nothing happening, waiting for GC to start
    GC_STAGE_START,      // First setup
    GC_STAGE_SCAN_ROOTS, // Trying to scan stack. Globals scanned as we exited idle.
    GC_STAGE_MARK_SWEEP, // Walk the graph, mark things as seen and scan as we go
    GC_STAGE_PRUNE
};

enum thread_state {
    THREAD_STATE_RUNNING,               // Busy running, don't interrupt
    THREAD_STATE_SUSPENDED,             // IO is in progress, so an external thread could scan this thread
    THREAD_STATE_SUSPENDED_SCAN,        // Thread is suspended, an external thread is scanning this one
    THREAD_STATE_EXITED
};



typedef struct {
    char *bump; // -size to get next object reference
    char *base; // until <base_pointer, then we need to ask for more
} bump_pointers_t;

thread_local struct gc_thread_info {
    atomic_int_fast32_t safe_point_request;
    int_fast32_t lag_counter;
    bool in_relocation;  // set while compaction evacuates objects: its target
                         // allocations may use the relocation reserve

    struct gc_thread_info *next;

    thread_roots_declaration_func_t thread_roots_declaration_func;
    void* thread_roots_context;

    bool roots_scanned;
    _Atomic(enum thread_state) thread_state;

    list_element_t  new_pages; // Circular list of pages waiting for next GC
    bump_pointers_t region_mutable;
    bump_pointers_t region_immutable;

    object_t **stack_lower_ptr; // Numerically lower pointer to the stack
    object_t **stack_upper_ptr; // Numerically higher pointer to the stack
    jmp_buf    saved_registers; // Expensive way to save the registers for GC
} gc_thread_info;

static _Atomic(struct gc_thread_info*) threads = NULL;
static enum gc_stage         stage = GC_STAGE_NOT_STARTED;
static uint32_t              epoch = 0; // Must never be 0, except now

// Bumped each time gc_fsa_prune drains pages_to_prune to empty (i.e., a full
// GC cycle has completed). Diagnostic only.
static _Atomic(uint64_t)     gc_cycle_count = 0;

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
// program's life. Only touched under fsa_lock (the scanner's own marking);
// the mutator-side barrier keeps its own reprocess ring.
enum { MARK_CHUNK_CAP = (GC_PAGE_SIZE - 2 * sizeof(void*)) / sizeof(object_t*) };
enum { MARK_FREELIST_KEEP = 4 };        // chunks cached across cycles
typedef struct mark_chunk {
    struct mark_chunk *prev;            // chunk below this one on the stack
    size_t             count;           // entries in use
    object_t          *slots[MARK_CHUNK_CAP];
} mark_chunk_t;
static mark_chunk_t *mark_top  = NULL;  // top chunk, NULL when the stack is empty
static mark_chunk_t *mark_free = NULL;  // recycled-chunk freelist (linked via ->prev)
static size_t        mark_free_count = 0;
static size_t        mark_worklist_count = 0;  // diagnostic depth (for [GC] stats)

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

static list_element_t pages_to_scan  = {&pages_to_scan, &pages_to_scan};
static list_element_t pages_to_prune = {&pages_to_prune, &pages_to_prune};

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
static list_element_t old_pages = {&old_pages, &old_pages};
static _Atomic(uint64_t) gc_alloc_clock = 0; // cumulative pages ever allocated
static size_t gc_promote_volume = 0;  // pages of allocation a page must stay
                                      // stable across to promote: eight young
                                      // turnovers, set at each prune's end.
static size_t gc_old_page_count   = 0;
static size_t gc_dirty_old_count  = 0;   // diagnostic: dirty-old pages this cycle
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
static size_t gc_cycle_survivors  = 0;   // pages surviving PRUNE this cycle
static size_t gc_cycle_survivor_slots = 0; // live SLOTS on young survivors (byte-honest)

// Pacing is stated in PAGES, and nothing else: per page allocated, the
// collector scans GC_PACE_SCAN_PAGES pages and prunes GC_PACE_PRUNE_RATIO
// times that. The progress guarantee is structural, not feedback-driven — with a
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
static uint64_t gc_pace_last_clock = 0;   // only touched under fsa_lock
static unsigned gc_pace_credit(void) {
    uint64_t now = atomic_load_explicit(&gc_alloc_clock, memory_order_relaxed);
    uint64_t backlog = now - gc_pace_last_clock;
    unsigned take = backlog > GC_PACE_CREDIT_MAX ? GC_PACE_CREDIT_MAX : (unsigned)backlog;
    gc_pace_last_clock += take;
    return take > 0 ? take : 1;
}


// --- GC diagnostics (set YAFL_GC_STATS to enable; prints to stderr).
// A sampled progress line every 512 page allocations, plus a [GC TIME]
// summary at exit: time inside gc_fsa per stage vs wall and process CPU.
extern size_t memory_watermark(void);
static _Atomic(uint64_t) gc_stat_mark_steps   = 0;  // gc_fsa_mark_sweep() invocations
static _Atomic(uint64_t) gc_stat_pages_popped = 0;  // pages popped + scanned in mark-sweep
static _Atomic(uint64_t) gc_stat_requeued     = 0;  // page_needs_scan() — re-scan requeues
static _Atomic(uint64_t) gc_stat_rq_drain     = 0;  //   ...from post-scan atomic-seen drain
static _Atomic(uint64_t) gc_stat_rq_repro     = 0;  //   ...from reprocess-ring drain
static _Atomic(uint64_t) gc_stat_overflows    = 0;  // reprocess-ring overflow whole-heap rescans
static _Atomic(uint64_t) gc_stat_prune_steps  = 0;  // gc_fsa_prune() invocations
static _Atomic(uint64_t) gc_stat_pages_freed  = 0;  // gc_page_free() calls
static _Atomic(uint64_t) gc_stat_page_allocs  = 0;  // gc_page_alloc() calls
static _Atomic(uint64_t) gc_stat_majors       = 0;  // major (full-heap) cycles completed
static _Atomic(uint64_t) gc_stat_cons_seeds   = 0;  // objects seeded live by conservative scan
/* Fine-grained mark/prune profiling (stats-gated, single FSA thread): object
   and pointer tallies, promotion outcomes, and tsc per mark/prune section —
   printed at exit as [GC PROF]/[GC PROMO] alongside the stats. */
static uint64_t gc_prof_objs, gc_prof_ptrs, gc_prof_passes, gc_prof_drained;
static uint64_t gc_prof_promote_ok, gc_prof_promote_dirty, gc_prof_block_unstable,
                gc_prof_block_volume, gc_prof_block_kind, gc_prof_defer;
static uint64_t gc_prof_t_drain, gc_prof_t_pages, gc_prof_t_merge, gc_prof_t_live, gc_prof_t_prune_rest;
static inline uint64_t gc_tsc(void) { unsigned lo, hi; __asm__ volatile("rdtsc" : "=a"(lo), "=d"(hi)); return ((uint64_t)hi << 32) | lo; }
#define GC_STAT_BUMP(c)\
    do { if (UNLIKELY(gc_stats_enabled))\
             atomic_fetch_add_explicit(&(c), 1, memory_order_relaxed);\
    } while (false)

// Charge the time since `last` (an rdtsc reading) to profile accumulator
// `acc`, then advance `last` to now — the per-section "lap" used to attribute
// mark/prune time. Companion to GC_STAT_BUMP: stats-gated, so it compiles to
// nothing measurable when YAFL_GC_STATS is off. `last` is passed explicitly
// rather than captured, so the macro reads no hidden local.
#define GC_PROF_LAP(acc, last)\
    do { if (UNLIKELY(gc_stats_enabled)) {\
             uint64_t _now = gc_tsc();\
             (acc) += _now - (last);\
             (last) = _now;\
         } } while (false)

// Nanoseconds spent inside gc_fsa, per stage (index = enum gc_stage). All GC
// work happens there, single-threaded under fsa_lock, so the sum is total
// collector time. Excludes mutator-side barrier checks and allocator memsets.
static _Atomic(uint64_t) gc_stat_stage_ns[8];
// Per-call latency histogram: log2(ns) buckets per stage (see gc_fsa's exit
// timing block and the [GC LAT] report). The bucket index uses
// __builtin_clzll, whose operand is unsigned long long; pin that to uint64_t
// (the type of the value being bucketed) so the width the log2 maths assumes
// can never silently diverge from clzll's operand on some future platform.
_Static_assert(sizeof(unsigned long long) == sizeof(uint64_t),
               "__builtin_clzll operand must be 64-bit for the [GC LAT] log2 bucketing");
enum { GC_LAT_BUCKETS = 24 };
static _Atomic(uint64_t) gc_stat_lat[8][GC_LAT_BUCKETS];
static _Atomic(uint64_t) gc_stat_fsa_calls = 0;
static struct timespec   gc_stats_t0;

// Page-occupancy survey (stats only): accumulated over each PRUNE as surviving
// pages stream past, snapshotted at cycle end. Index 0 = immutable, 1 = mutable.
// "Sparse" = under 25% live — candidates for any future reclamation of
// mostly-empty pages. Live slot counts use the objects/seen bitmaps alone
// (object extent = start bit to next start bit), never vtables.
static size_t gc_occ_pages[2], gc_occ_live[2], gc_occ_sparse[2], gc_occ_sparse_free[2], gc_occ_large;
static size_t gc_snap_pages[2], gc_snap_live[2], gc_snap_sparse[2], gc_snap_sparse_free[2], gc_snap_large;
// Why is an immutable sparse page sparse? fwd = compacted earlier, only
// forwarders remain (lazy-fixup residue); pin = conservative root pinned it
// this cycle; oth = eligible but blocked some other way (object-count guard).
static size_t gc_occ_sparse_fwd, gc_occ_sparse_pin, gc_occ_sparse_oth;
static size_t gc_snap_sparse_fwd, gc_snap_sparse_pin, gc_snap_sparse_oth;

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

// --- Heap hunt (YAFL_GC_HUNT, diagnostics only) ------------------------------
//
// Post-mortem retention analysis, printed at exit alongside the stats when
// YAFL_GC_HUNT is set (requires YAFL_GC_STATS). Three stages:
//   1. CENSUS: every live object bucketed by vtable name with counts — the
//      first question is always "what IS all this?".
//   2. HEADS: for the bucket named by the env value (substring match; "1" =
//      biggest bucket), find members no same-type member points to — the
//      entry points of chains/lists, however long.
//   3. HOLDERS: one full-heap scan reporting each head's first heap referrer,
//      plus a conservative stack/register sweep. Caveat: the sweep also sees
//      the hunter's own frame — ignore pins within a few hundred bytes of
//      the reported hunter SP.
// Found on its first outing: completed tasks retaining dead capture graphs
// (fixed by deferred resumption) and per-construction unit-enum boxes (fixed
// by static promotion). Zero cost when the env var is unset.
static vtable_t* _hunt_vt(object_t* o) {
    vtable_t* vt = o->vtable;
    while (vt && vtable_is_forward(vt)) vt = ((object_t*)vt)->vtable;
    return vt;
}
static void _hunt_each_live(void (*fn)(object_t*, void*), void* arg) {
    extern char* _memory_heap_base;
    size_t wm = memory_watermark();
    for (size_t pi = 0; pi < wm; pi++) {
        gc_page_t* page = (gc_page_t*)(_memory_heap_base + pi * GC_PAGE_SIZE);
        if (!memory_pages_is_alloc_head(page) || page->head.tag != PAGE_MAGIC_NUMBER) continue;
        for (unsigned index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index) {
            mask_bits_t starts = page->head.objects.a[index];
            unsigned offset = index * GC_MASK_SIZE;
            while (starts) {
                unsigned slot = __builtin_ctzll(starts) + offset;
                starts &= starts - 1;
                fn((object_t*)&page->slots[slot], arg);
            }
        }
        if (page->head.pages > 1) pi += page->head.pages - 1;
    }
}
struct _hunt_ref { object_t* target; object_t* referrer; const char* via; int count; };
static void _hunt_scan_fields(object_t* o, void* arg) {
    struct _hunt_ref* r = (struct _hunt_ref*)arg;
    vtable_t* vt = _hunt_vt(o);
    if (!vt || vtable_is_forward(o->vtable)) return;
    uint64_t m = vt->object_pointer_locations;
    while (m) {
        unsigned i = (unsigned)__builtin_ctzll(m);
        m &= m - 1;
        if (((object_t**)o)[i] == r->target) {
            r->count++;
            if (!r->referrer) {
                r->referrer = o;
                r->via = vt->name;
            }
        }
    }
    if (vt->array_el_pointer_locations) {
        uint32_t len = *(uint32_t*)&((char*)o)[vt->array_len_offset];
        char* arr = ((char*)o) + vt->object_size;
        for (; len-- > 0; arr += vt->array_el_size) {
            uint64_t am = vt->array_el_pointer_locations;
            while (am) {
                unsigned i = (unsigned)__builtin_ctzll(am);
                am &= am - 1;
                if (((object_t**)arr)[i] == r->target) {
                    r->count++;
                    if (!r->referrer) {
                        r->referrer = o;
                        r->via = vt->name;
                    }
                }
            }
        }
    }
}
static int _hunt_scan_pins(object_t* target) {
    int hits = 0;
    for (struct gc_thread_info* t = threads; t != NULL; t = t->next) {
        for (object_t** p = t->stack_lower_ptr; p && p < t->stack_upper_ptr; p++) {
            if (*p == target) {
                fprintf(stderr, "[HUNT]     PIN stack thread=%p at %p\n", (void*)t, (void*)p);
                hits++;
            }
        }
        object_t** rl = (object_t**)&t->saved_registers[0];
        object_t** rh = (object_t**)&t->saved_registers[1];
        for (object_t** p = rl; p < rh; p++) {
            if (*p == target) {
                fprintf(stderr, "[HUNT]     PIN register thread=%p slot=%ld\n", (void*)t, (long)(p - rl));
                hits++;
            }
        }
    }
    return hits;
}
static object_t** _hunt_members;
static char*      _hunt_pointed;
static size_t     _hunt_nmembers;
static const char* _hunt_member_name;
static int _hunt_cmp_ptr(const void* a, const void* b) {
    uintptr_t x = *(const uintptr_t*)a, y = *(const uintptr_t*)b;
    return x < y ? -1 : x > y ? 1 : 0;
}
static long _hunt_member_idx(object_t* o) {
    size_t lo = 0, hi = _hunt_nmembers;
    while (lo < hi) {
        size_t mid = (lo + hi) / 2;
        if ((uintptr_t)_hunt_members[mid] < (uintptr_t)o) lo = mid + 1;
        else hi = mid;
    }
    return (lo < _hunt_nmembers && _hunt_members[lo] == o) ? (long)lo : -1;
}
static void _hunt_collect_members(object_t* o, void* arg) {
    (void)arg;
    vtable_t* vt = _hunt_vt(o);
    if (vt && vt->name && vt->name == _hunt_member_name)
        _hunt_members[_hunt_nmembers++] = o;
}
static void _hunt_mark_pointed(object_t* o, void* arg) {
    (void)arg;
    vtable_t* vt = _hunt_vt(o);
    if (!vt || vtable_is_forward(o->vtable) || !vt->name || vt->name != _hunt_member_name) return;
    uint64_t m = vt->object_pointer_locations;
    while (m) {
        unsigned i = (unsigned)__builtin_ctzll(m);
        m &= m - 1;
        long idx = _hunt_member_idx(((object_t**)o)[i]);
        if (idx >= 0) _hunt_pointed[idx] = 1;
    }
}
struct _hunt_bkt { const char* name; size_t count; object_t* example; };
static struct _hunt_bkt _hunt_bkts[128];
static int _hunt_nbkts = 0;
static void _hunt_census_one(object_t* o, void* arg) {
    (void)arg;
    vtable_t* vt = _hunt_vt(o);
    const char* nm = (vt && !vtable_is_forward(o->vtable)) ? (vt->name ? vt->name : "?") : "(fwd)";
    int b;
    for (b = 0; b < _hunt_nbkts; b++)
        if (_hunt_bkts[b].name == nm) break;
    if (b == _hunt_nbkts && _hunt_nbkts < 128) {
        _hunt_bkts[_hunt_nbkts].name = nm;
        _hunt_bkts[_hunt_nbkts].count = 0;
        _hunt_bkts[_hunt_nbkts].example = o;
        _hunt_nbkts++;
    }
    if (b < 128) {
        _hunt_bkts[b].count++;
        _hunt_bkts[b].example = o;
    }
}
static void _hunt_run(void) {
    if (!getenv("YAFL_GC_HUNT")) return;   // see the heap-hunt comment above
    _hunt_each_live(_hunt_census_one, NULL);
    fprintf(stderr, "[HUNT] census:\n");
    for (int b = 0; b < _hunt_nbkts; b++)
        fprintf(stderr, "[HUNT]   %-50s count=%zu example=%p\n", _hunt_bkts[b].name, _hunt_bkts[b].count, (void*)_hunt_bkts[b].example);
    // Find the chosen bucket (YAFL_GC_HUNT substring; "1" = biggest), then
    // locate its HEADS — members no other member points to — and report who
    // holds each head (heap referrer, or stack/register pin).
    const char* want = getenv("YAFL_GC_HUNT");
    struct _hunt_bkt* big = NULL;
    for (int b = 0; b < _hunt_nbkts; b++) {
        if (want && want[0] != '1' && (!_hunt_bkts[b].name || !strstr(_hunt_bkts[b].name, want))) continue;
        if (!big || _hunt_bkts[b].count > big->count) big = &_hunt_bkts[b];
    }
    if (!big) return;
    fprintf(stderr, "[HUNT] chasing bucket %s (count=%zu)\n", big->name, big->count);
    _hunt_members = malloc(big->count * sizeof(object_t*));
    _hunt_pointed = calloc(big->count, 1);
    _hunt_nmembers = 0;
    _hunt_member_name = big->name;
    _hunt_each_live(_hunt_collect_members, NULL);
    qsort(_hunt_members, _hunt_nmembers, sizeof(object_t*), _hunt_cmp_ptr);
    _hunt_each_live(_hunt_mark_pointed, NULL);
    size_t nheads = 0;
    object_t* heads[8];
    for (size_t i = 0; i < _hunt_nmembers; i++) {
        if (!_hunt_pointed[i]) {
            if (nheads < 8) heads[nheads] = _hunt_members[i];
            nheads++;
        }
    }
    fprintf(stderr, "[HUNT] members=%zu heads=%zu\n", _hunt_nmembers, nheads);
    {
        volatile char sp_marker = 0;
        fprintf(stderr, "[HUNT] hunter SP ~= %p\n", (void*)&sp_marker);
    }
    for (size_t h = 0; h < nheads && h < 8; h++) {
        struct _hunt_ref r = { heads[h], NULL, NULL, 0 };
        _hunt_each_live(_hunt_scan_fields, &r);
        vtable_t* rvt = r.referrer ? _hunt_vt(r.referrer) : NULL;
        fprintf(stderr, "[HUNT] head[%zu] %p: heap refs=%d holder=%p (%s) pins=%d\n",
                h, (void*)heads[h], r.count, (void*)r.referrer,
                rvt && rvt->name ? rvt->name : "-", _hunt_scan_pins(heads[h]));
    }
    free(_hunt_members);
    free(_hunt_pointed);
}

static void gc_stats_report(void) {
    _hunt_run();
    struct timespec t1, cpu;
    clock_gettime(CLOCK_MONOTONIC, &t1);
    clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &cpu);
    double wall = (t1.tv_sec - gc_stats_t0.tv_sec) + (t1.tv_nsec - gc_stats_t0.tv_nsec) / 1e9;
    double cpus = cpu.tv_sec + cpu.tv_nsec / 1e9;
    double gc = 0, mark, prune, roots;
    for (unsigned i = 0; i < 8; ++i) gc += atomic_load(&gc_stat_stage_ns[i]) / 1e9;
    roots = atomic_load(&gc_stat_stage_ns[GC_STAGE_SCAN_ROOTS]) / 1e9;
    mark  = atomic_load(&gc_stat_stage_ns[GC_STAGE_MARK_SWEEP]) / 1e9;
    prune = atomic_load(&gc_stat_stage_ns[GC_STAGE_PRUNE]) / 1e9;
    fprintf(stderr,
        "[GC TIME] gc=%.3fs (roots=%.3f mark=%.3f prune=%.3f other=%.3f) "
        "wall=%.3fs cpu=%.3fs | gc/wall=%.1f%% gc/cpu=%.1f%% | fsa_calls=%llu cycles=%llu\n",
        gc, roots, mark, prune, gc - roots - mark - prune,
        wall, cpus,
        wall > 0 ? 100.0 * gc / wall : 0.0,
        cpus > 0 ? 100.0 * gc / cpus : 0.0,
        (unsigned long long)atomic_load(&gc_stat_fsa_calls),
        (unsigned long long)atomic_load(&gc_cycle_count));

    // Per-call latency distribution by stage: percentile bounds read off the
    // log2 histogram (a bucket b means "< 2^(b+1) ns"). The spread between
    // p50 and p99 is the call-cost (un)predictability we tune pacing for.
    static const char *lat_name[8] = {
        [GC_STAGE_SCAN_ROOTS] = "roots", [GC_STAGE_MARK_SWEEP] = "mark",
        [GC_STAGE_PRUNE] = "prune" };
    for (unsigned s = 0; s < 8; ++s) {
        if (!lat_name[s]) continue;
        uint64_t n = 0;
        for (unsigned b = 0; b < GC_LAT_BUCKETS; ++b) n += atomic_load(&gc_stat_lat[s][b]);
        if (n == 0) continue;
        unsigned p50 = 0, p90 = 0, p99 = 0, pmax = 0;
        uint64_t acc = 0;
        for (unsigned b = 0; b < GC_LAT_BUCKETS; ++b) {
            uint64_t c = atomic_load(&gc_stat_lat[s][b]);
            if (c == 0) continue;
            acc += c;
            if (p50 == 0 && acc * 2 >= n)       p50 = b + 1;
            if (p90 == 0 && acc * 10 >= n * 9)  p90 = b + 1;
            if (p99 == 0 && acc * 100 >= n * 99) p99 = b + 1;
            pmax = b + 1;
        }
        fprintf(stderr, "[GC LAT] %-5s calls=%llu p50<2^%uns p90<2^%u p99<2^%u max<2^%u\n",
                lat_name[s], (unsigned long long)n, p50, p90, p99, pmax);
    }

    // Page-occupancy snapshot of the last completed cycle. "sparse" = <25%
    // live; its KB figure is the space those pages are wasting.
    const char* cls_name[2] = { "imm", "mut" };
    char occ_line[256]; size_t off = 0;
    for (int cls = 0; cls < 2; ++cls) {
        double pct = gc_snap_pages[cls]
            ? 100.0 * (double)gc_snap_live[cls] / ((double)gc_snap_pages[cls] * SLOTS_PER_PAGE) : 0.0;
        off += (size_t)snprintf(occ_line + off, sizeof occ_line - off,
            "%s: n=%zu live=%.0f%% sparse=%zu (waste %zu KB) | ",
            cls_name[cls], gc_snap_pages[cls], pct,
            gc_snap_sparse[cls],
            gc_snap_sparse_free[cls] * sizeof(slot_t) / 1024);
    }
    fprintf(stderr, "[GC PROMO] ok=%llu dirty=%llu unstable=%llu volume=%llu kind=%llu defer=%llu\n",
            (unsigned long long)gc_prof_promote_ok, (unsigned long long)gc_prof_promote_dirty,
            (unsigned long long)gc_prof_block_unstable, (unsigned long long)gc_prof_block_volume,
            (unsigned long long)gc_prof_block_kind, (unsigned long long)gc_prof_defer);
    fprintf(stderr, "[GC PROF] objs=%llu ptrs=%llu drained=%llu passes=%llu | tsc: drain=%llu merge=%llu pages=%llu live=%llu prune_rest=%llu\n",
            (unsigned long long)gc_prof_objs, (unsigned long long)gc_prof_ptrs,
            (unsigned long long)gc_prof_drained, (unsigned long long)gc_prof_passes,
            (unsigned long long)gc_prof_t_drain, (unsigned long long)gc_prof_t_merge,
            (unsigned long long)gc_prof_t_pages, (unsigned long long)gc_prof_t_live,
            (unsigned long long)gc_prof_t_prune_rest);
    fprintf(stderr, "[GC PAGES] last cycle: %slarge=%zu pages | imm-sparse: fwd=%zu pin=%zu oth=%zu | old=%zu dirty=%zu pages majors=%llu\n",
            occ_line, gc_snap_large,
            gc_snap_sparse_fwd, gc_snap_sparse_pin, gc_snap_sparse_oth,
            gc_old_page_count, gc_dirty_old_count,
            (unsigned long long)atomic_load(&gc_stat_majors));
    size_t scav_ret, scav_rec, scav_cold, scav_rec_runs;
    memory_scavenge_stats(&scav_ret, &scav_rec, &scav_cold, &scav_rec_runs);
    fprintf(stderr, "[GC SCAV] returned=%zu reclaimed=%zu (runs=%zu) cold_now=%zu (pages)\n",
            scav_ret, scav_rec, scav_rec_runs, scav_cold);
}

static void gc_stats_tick(void) {
    if (LIKELY(!gc_stats_enabled)) return;
    uint64_t n = atomic_fetch_add_explicit(&gc_stat_page_allocs, 1, memory_order_relaxed) + 1;
    if ((n & 511) != 0) return;   // sample every 512 page allocations
    unsigned scanq = 0;
    for (list_element_t *n = pages_to_scan.next; n != &pages_to_scan && scanq < 9999; n = n->next)
        scanq++;
    size_t scav_ret, scav_rec, scav_cold, scav_rec_runs;
    memory_scavenge_stats(&scav_ret, &scav_rec, &scav_cold, &scav_rec_runs);
    fprintf(stderr,
        "[GC] allocs=%llu watermark=%llu live=%llu cycles=%llu stage=%d epoch=%u "
        "wl=%u scanq=%u "
        "mark_steps=%llu popped=%llu requeued=%llu overflows=%llu "
        "rq_drain=%llu rq_repro=%llu prune_steps=%llu freed=%llu "
        "scav_ret=%zu scav_rec=%zu cold=%zu\n",
        (unsigned long long)n,
        (unsigned long long)memory_watermark(),
        (unsigned long long)memory_count(),
        (unsigned long long)atomic_load(&gc_cycle_count),
        (int)stage, (unsigned)epoch,
        (unsigned)mark_worklist_count, scanq,
        (unsigned long long)atomic_load(&gc_stat_mark_steps),
        (unsigned long long)atomic_load(&gc_stat_pages_popped),
        (unsigned long long)atomic_load(&gc_stat_requeued),
        (unsigned long long)atomic_load(&gc_stat_overflows),
        (unsigned long long)atomic_load(&gc_stat_rq_drain),
        (unsigned long long)atomic_load(&gc_stat_rq_repro),
        (unsigned long long)atomic_load(&gc_stat_prune_steps),
        (unsigned long long)atomic_load(&gc_stat_pages_freed),
        scav_ret, scav_rec, scav_cold);
}


// DEBUG: when set, allocation does NOT drive the GC FSA, so a test can step the
// collector by hand (gc_debug_step) and pin down exact interleavings.
EXPORT bool gc_debug_manual_mode = false;

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
            atomic_fetch_or(&gc_thread_info.safe_point_request, GC_SAFE_POINT_CATCH_UP);
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
    // zeroed individually at allocation in _object_alloc. The release fence
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

// Zero exactly the slots the new object occupies, at the point of allocation:
// the zero-writes land in L1 immediately under the field writes that follow.
// (The old scheme memset whole pages at claim time; by the time a page's
// later objects were carved out those lines had been evicted, so every first
// field write missed again.) The zero state is load-bearing — see
// object_create — and it is always written HERE, never inherited from the
// kernel's zero-fill promise (a future MADV_FREE would break that promise).
static inline void zero_object_slots(void *object, size_t actual_size) {
    slot_t *s = object;
    for (size_t k = 0; k < actual_size / sizeof(slot_t); ++k)
        s[k] = (slot_t){0};
}

static NOINLINE_DEBUG void *_object_alloc(size_t size, bool is_mutable) {
    size_t actual_size = (size + sizeof(slot_t) - 1) / sizeof(slot_t) * sizeof(slot_t);

    if (actual_size > MAX_OBJECT_SIZE) {
        // Object exceeds a single page's slot region: allocate a dedicated
        // multi-page run and treat the whole slot region as one object. Only
        // bit 0 of the head page's `objects` bitmap is set; subsequent
        // physical pages have no header of their own.
        size_t page_count = (sizeof(page_head_t) + actual_size + GC_PAGE_SIZE - 1) / GC_PAGE_SIZE;
        gc_page_t* page = gc_page_alloc(page_count);
        zero_object_slots(page->slots, actual_size);   // before the bitmap makes it findable
        page->head.mutable = is_mutable;
        page->head.objects.a[0] = 1;
        list_link(&gc_thread_info.new_pages, (list_element_t*)&page->head.list);
        // Snapshot-smear guard — see the bump path below for the rationale.
        if (UNLIKELY(gc_thread_info.safe_point_request & GC_SAFE_POINT_SCAN_ROOTS))
            atomic_bitmap_fetch_set(&page->head.scanner.atomic_seen, 0);
        return page->slots;
    }

    bump_pointers_t *bp = is_mutable
        ? &gc_thread_info.region_mutable
        : &gc_thread_info.region_immutable;

    if (UNLIKELY((size_t)(bp->bump - bp->base) < actual_size)) {
        gc_page_t* new_page = gc_page_alloc(1);

        new_page->head.mutable = is_mutable;
        bp->base = (char*)(new_page->slots);
        bp->bump = (char*)(new_page->slots + SLOTS_PER_PAGE);

        list_link(&gc_thread_info.new_pages, (list_element_t*)&new_page->head.list);
    }

    object_t *object = (object_t*)(bp->bump -= actual_size);
    zero_object_slots(object, actual_size);   // before the bitmap makes it findable

    gc_page_t *page ; ptrdiff_t slot ;
    object_get_page_and_slot(object, &page, &slot);
    bitmap_fetch_set(&page->head.objects, slot);

    // Snapshot-smear guard: between a cycle opening and THIS thread's root
    // scan, objects allocated here land on pages that will be taken into the
    // current cycle's collection pool — no birth protection — and the stack
    // scan that would find them happens too late (the snapshot is ragged).
    // Allocate BLACK for exactly that window: mark the object seen at birth.
    // The window closes when this thread's scan clears the flag, so the cost
    // outside it is one thread-local load and a not-taken branch.
    if (UNLIKELY(gc_thread_info.safe_point_request & GC_SAFE_POINT_SCAN_ROOTS))
        atomic_bitmap_fetch_set(&page->head.scanner.atomic_seen, slot);

    return object;
}

EXPORT void* object_create(vtable_t *vtable) {
    assert(vtable->array_el_size == 0);
    object_t *object = _object_alloc(vtable->object_size, vtable->is_mutable);
    // Every field is already zero (_object_alloc zeroes the object's slots).
    // That NULL state is load-bearing — the generated code writes each pointer
    // field through the GC write barrier, which marks the field's PRIOR value,
    // and a partially-initialised object may be scanned; NULL is safe, garbage
    // is not.
    object->vtable = vtable;
    LOG(ULTRA, "ALLOC(0x%lx) -> %s", (uintptr_t)object, vtable->name);
    return object;
}

EXPORT void* array_create(vtable_t *vtable, int32_t length) {
    assert(length >= 0);
    assert(vtable->array_el_size != 0);
    size_t total = vtable->object_size + (size_t)vtable->array_el_size * (size_t)length;
    object_t *object = _object_alloc(total, vtable->is_mutable);
    // The whole object is already zero (_object_alloc zeroes its slots).
    // That matters: a pointer-bearing object (e.g. a heap state frame) may be
    // scanned before every field is written — NULL is safe, garbage is not.
    object->vtable = vtable;
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

EXPORT vtable_t *object_get_vtable(object_t *object) {
    vtable_t *vt = object->vtable;
    while (UNLIKELY(vtable_is_forward(vt))) {
        object_t *next_object = (object_t*)vt;
        vt = next_object->vtable;
    }
    return vt;
}

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
#ifdef STACK_GROWS_DOWN
    gc_thread_info.stack_upper_ptr = stack_anchor;
#else
    gc_thread_info.stack_lower_ptr = stack_anchor;
#endif

    gc_thread_info.thread_roots_declaration_func = thread_roots_declaration_func;
    gc_thread_info.thread_roots_context = thread_roots_context;

    gc_thread_info.next = threads;
    gc_thread_info.thread_state = THREAD_STATE_RUNNING;

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

            size_t size = object_get_size((object_t*)&page->slots[slot]);
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
    gc_thread_info.in_relocation = true;
    for (unsigned index = 0; index < object_count; ++index) {
        object_t *object = (object_t*)&page->slots[objects[index].o];
        size_t      size = objects[index].s;

        object_t *target = _object_alloc(size, false);       // Allocate new object
        memcpy(target, object, size);                        // Copy contents across
        object->vtable = (vtable_t*)target;                  // Forwarding pointer: a heap
                                                             // address here means "moved"
    }
    gc_thread_info.in_relocation = false;
}
#endif








static bool gc_object_is_on_heap_slow(object_t *object) {
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






static NOINLINE_DEBUG enum gc_stage gc_fsa_start() {
    if (++epoch == 0)
        epoch = 1;

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

    // NB: the declared global roots are NOT scanned here. They are scanned at the
    // END of SCAN_ROOTS, after every stack has been scanned and every thread's
    // new pages have been promoted into the scan set. Scanning them at cycle
    // start (before promotion) loses an object that is stored into a declared
    // root after the start but lands on a page promoted this cycle: the root
    // snapshot predates the store, so nothing marks it, yet its page is prunable.
    for (struct gc_thread_info *thread = threads; thread != NULL; thread = thread->next) {
        atomic_fetch_or(&thread->safe_point_request, GC_SAFE_POINT_SCAN_ROOTS);
        thread->roots_scanned = false;
    }

    return GC_STAGE_SCAN_ROOTS;
}






static NOINLINE_DEBUG void gc_fsa_scan_roots$scan_range(object_t **range_ptr, object_t **range_end) {
    for (; range_ptr != range_end; range_ptr++) {
        object_t *object = *range_ptr;
        if (gc_object_is_on_heap_slow(object)) {
            // Conservative candidate: a stale stack slot can point into a
            // freed page that a concurrent gc_page_alloc is re-initialising
            // under us, so mark it tolerantly — no asserting helpers. A
            // spurious mark lands either on a dying page (harmless) or on a
            // real live object (over-retention, also harmless); missing a
            // REAL object is impossible because live pages are never freed.
            // The reprocess-queue handling that atomic_gc_object_mark_as_seen
            // does is not needed here: during SCAN_ROOTS no page has been
            // mark-swept this epoch yet.
            gc_page_t* page = (gc_page_t*)((uintptr_t)object &~ (uintptr_t)(GC_PAGE_SIZE-1));
            ptrdiff_t  slot = (slot_t*)object - page->slots;
            if (page->head.old) continue;   // old generation: implicitly live, never pruned
            page->head.scanner.pinned = true;
            if (!atomic_bitmap_fetch_set(&page->head.scanner.atomic_seen, slot))
                GC_STAT_BUMP(gc_stat_cons_seeds);   // diagnostic: conservative root seeds
        }
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
        thread->region_immutable.base = thread->region_mutable.base = NULL;
        thread->region_immutable.bump = thread->region_mutable.bump = NULL;
        // Scan stack and registers
        gc_fsa_scan_roots$scan_range(thread->stack_lower_ptr, thread->stack_upper_ptr);
        gc_fsa_scan_roots$scan_range((object_t**)&thread->saved_registers[0], (object_t**)&thread->saved_registers[1]);
        // Thread library has some stuff
        thread->thread_roots_declaration_func(thread->thread_roots_context, atomic_gc_object_seen_by_field);
        // Release the thread state
        atomic_fetch_and(&thread->safe_point_request, ~GC_SAFE_POINT_SCAN_ROOTS);
        atomic_store(&thread->thread_state, old_state);
        thread->lag_counter = 0;
    }

    for (thread = threads; thread != NULL; thread = thread->next)
        if (!thread->roots_scanned)
            return GC_STAGE_SCAN_ROOTS;

    // Every stack has now been scanned and every thread's new pages promoted into
    // the scan set. Scan the declared global roots NOW, at this single consistent
    // point — so an object published into a declared root during SCAN_ROOTS, on a
    // page that was promoted this cycle, is marked rather than pruned.
    declare_roots_yafl(atomic_gc_object_seen_by_field);
    declare_roots_thread(atomic_gc_object_seen_by_field);

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

    assert(!list_empty(&pages_to_scan));
    assert(list_empty(&pages_to_prune));

    return GC_STAGE_MARK_SWEEP;
}





static void gc_fsa_mark_sweep$page_needs_scan(gc_page_t *page) {
    GC_STAT_BUMP(gc_stat_requeued);
    page->head.scanner.processed_by_epoch = 0;
    list_unlink((list_element_t*)&page->head.list);
    list_link(&pages_to_scan, (list_element_t*)&page->head.list);
}

static void gc_fsa_mark_sweep$mark_object(object_t *object) {
    if (UNLIKELY(gc_stats_enabled)) gc_prof_ptrs++;
    // Mark the target object
    gc_page_t *page; ptrdiff_t slot;
    object_get_page_and_slot(object, &page, &slot);
    if (page->head.old) return;   // old generation: implicitly live in minor cycles
    bool was_set = bitmap_fetch_set(&page->head.scanner.seen, slot);

    // Newly marked on a page the scanner already finished this epoch: a
    // back-edge. Push the object for direct scanning — the per-page drain in
    // gc_fsa_mark_sweep resolves it (and anything it reaches) before the page
    // that found it is considered done. The seen bit set above keeps it live
    // for prune regardless of which page it sits on.
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

// Debug (YAFL_GC_POISON): catch a use-after-free cleanly — a live object being
// scanned whose GC pointer field references a reclaimed (poisoned) object.
// Aborts with the offending edge instead of faulting deep in the scanner.
static void _dbg_dangle_check(object_t* object) {
    // Follow forwarding to the real vtable; the field walk below still reads
    // the payload at `object` itself (a forwarder's old payload mirrors the
    // copy's layout until fixup rewrites it).
    vtable_t* vt = object->vtable;
    while (UNLIKELY(vtable_is_forward(vt)))
        vt = ((object_t*)vt)->vtable;
    uint64_t m = vt->object_pointer_locations;
    while (m) {
        unsigned i = (unsigned)__builtin_ctzll(m); m &= m-1;
        object_t* child = ((object_t**)object)[i];
        uintptr_t a = (uintptr_t)child;
        if (!a || (a & (GC_SLOT_SIZE-1)) || (a & PTR_TAG_MASK)) continue;
        gc_page_t* cpg = (gc_page_t*)(a & ~(uintptr_t)(GC_PAGE_SIZE-1));
        if (!memory_pages_is_alloc_head(cpg) || cpg->head.tag != PAGE_MAGIC_NUMBER) continue;
        if (*(uint64_t*)child != 0x4242424242424242ULL) continue;
        fprintf(stderr, "\nDANGLE cycle=%llu: live %p (vt=%s) field#%u -> reclaimed %p\n",
                (unsigned long long)atomic_load(&gc_cycle_count),
                (void*)object, vt->name, i, (void*)child);
        fflush(stderr);
        abort();
    }
}

static void gc_fsa_mark_sweep$scan_object(object_t *object) {
    if (UNLIKELY(gc_stats_enabled)) gc_prof_objs++;
    if (UNLIKELY(gc_poison_enabled))
        _dbg_dangle_check(object);
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

    // A mutable container's pointer slots may be written by the mutator in
    // parallel with this scan, so the GC must not snap them to forwarding
    // targets (it would race / clobber the mutator's store). Mark through but
    // don't rewrite. `vt` is the resolved (forwarding-followed) vtable and
    // carries the same mutability bit object_create used to place the object on
    // a mutable page, so it is authoritative without a separate page lookup.
    bool fixup = !vt->is_mutable;

    // Scan references
    if (vt->object_pointer_locations) {
        gc_fsa_mark_sweep$scan_elements((object_t**)object, vt->object_pointer_locations, fixup);
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

static NOINLINE_DEBUG enum gc_stage gc_fsa_mark_sweep() {
    GC_STAT_BUMP(gc_stat_mark_steps);
    const unsigned step_pages = gc_step_base * gc_pace_credit();
    uint64_t _t0 = gc_stats_enabled ? gc_tsc() : 0;

    for (unsigned count = 0; count < step_pages; ++count) {
        gc_page_t *page = (gc_page_t*)list_pop(&pages_to_scan);
        if (page == NULL) break;
        GC_STAT_BUMP(gc_stat_pages_popped);
        assert(page->head.scanner.processed_by_epoch != epoch);

        GC_PROF_LAP(gc_prof_t_merge, _t0);
        if (bitmap_or_test_reset_all(&page->head.scanner.seen, &page->head.scanner.atomic_seen)) {
            while (gc_fsa_mark_sweep$scan_page(page)) {
                if (UNLIKELY(gc_stats_enabled)) gc_prof_passes++;
            }
        }

        page->head.scanner.processed_by_epoch = epoch;
        list_link(&pages_to_prune, (list_element_t*)&page->head.list);
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
        if (bitmap_or_test_source_reset_all(&page->head.scanner.seen, &page->head.scanner.atomic_seen)) {
            GC_STAT_BUMP(gc_stat_rq_drain);
            gc_fsa_mark_sweep$page_needs_scan(page);
        }
    }

    // Move re-process pages back on to the scan list
    while (reprocess_page_head < reprocess_page_tail) {
        size_t index = atomic_fetch_add(&reprocess_page_head, 1);
        gc_page_t *page;
        do {page = atomic_exchange(&reprocess_page_list[index % REPROCESS_PAGE_COUNT], NULL);
        } while (page == NULL);
        GC_STAT_BUMP(gc_stat_rq_repro);
        gc_fsa_mark_sweep$page_needs_scan(page);
    }

    // More work needs to happen. The worklist is always empty here — it is
    // drained per page above — so only the scan list governs continuation.
    if (!list_empty(&pages_to_scan)) {
        return GC_STAGE_MARK_SWEEP;
    }

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
        list_move(&pages_to_scan, &pages_to_prune);
        epoch = epoch==UINT32_MAX ? 1 : epoch+1;
        return GC_STAGE_MARK_SWEEP;
    }

    // All done
    gc_write_barrier_requested = false;
    return GC_STAGE_PRUNE;
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
            // Non-compacted page: the vtable word is a real vtable.
            vtable_t *vt = object->vtable;

            ptr_mask_t m = vt->object_pointer_locations;
            while (m) {
                unsigned i = __builtin_ctzll(m); m &= m-1;
                object_t *child = ((object_t**)object)[i];
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

static NOINLINE_DEBUG enum gc_stage gc_fsa_prune() {
    GC_STAT_BUMP(gc_stat_prune_steps);
    const unsigned step_pages = gc_step_base * GC_PACE_PRUNE_RATIO * gc_pace_credit();
    for (unsigned count = 0; count < step_pages; ++count) {
        gc_page_t *page = (gc_page_t*)list_pop(&pages_to_prune);
        if (page == NULL) break;
        assert(page->head.scanner.processed_by_epoch == epoch);

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
            gc_cycle_survivors += page->head.pages;
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
            list_unlink((list_element_t*)&page->head.list);
            list_link(&pages_to_scan, (list_element_t*)&page->head.list);
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
                        if (UNLIKELY(gc_stats_enabled)) gc_prof_promote_ok++;
                        page->head.dirty_old = false;
                        // Belt-and-braces: the only road back into the
                        // rotation (major demotion) resets these anyway.
                        page->head.refs_defer = page->head.refs_backoff = 0;
                        list_unlink((list_element_t*)&page->head.list);
                        list_link(&old_pages, (list_element_t*)&page->head.list);
                        page->head.old = true;
                        gc_old_page_count += 1;
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
                gc_cycle_survivor_slots += page_live_slots;
            if (UNLIKELY(gc_stats_enabled)) gc_prof_t_prune_rest += gc_tsc() - _tp0;
        } else {
            assert(bitmap_test_all(&page->head.scanner.atomic_seen) == false);
            gc_page_free(page);
        }
    }

    if (list_empty(&pages_to_prune)) {
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

        // Hand excess free pages back to the OS now that the prune has
        // settled the live set: warm slack retained = three young turnovers,
        // floored (see GC_SCAVENGE_RETAIN_FLOOR).
        size_t slack = young * 3;
        memory_scavenge(slack > GC_SCAVENGE_RETAIN_FLOOR ? slack : GC_SCAVENGE_RETAIN_FLOOR,
                        GC_SCAVENGE_BUDGET);

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
        return GC_STAGE_IDLE; // All done
    }
    return GC_STAGE_PRUNE;
}






static atomic_bool fsa_lock;
static NOINLINE_DEBUG bool gc_fsa() {
    assert(gc_thread_info.thread_state == THREAD_STATE_RUNNING);

    bool expected = false;
    if (!atomic_compare_exchange_strong(&fsa_lock, &expected, true))
        return false;

    struct timespec t_in;
    enum gc_stage entry_stage = stage;
    if (gc_stats_enabled) clock_gettime(CLOCK_MONOTONIC, &t_in);

    switch (stage) {
        case GC_STAGE_NOT_STARTED:
            break;

        case GC_STAGE_IDLE:
            // No dwell: the system is in a permanent GC cycle, so IDLE is
            // just the boundary between one cycle and the next — the next
            // allocation-driven step starts the new cycle immediately. The
            // state exists (rather than chaining PRUNE -> START directly)
            // so stepped tests can detect cycle boundaries.
            LOG(TRACE, "GC_STAGE_IDLE");
            stage = GC_STAGE_START;
            break;

        case GC_STAGE_START:
            LOG(TRACE, "GC_STAGE_START");
            stage = gc_fsa_start();
            break;

        case GC_STAGE_SCAN_ROOTS:
            LOG(TRACE, "GC_STAGE_SCAN_ROOTS");
            stage = gc_fsa_scan_roots();
            break;

        case GC_STAGE_MARK_SWEEP:
            LOG(TRACE, "GC_STAGE_MARK_SWEEP");
            stage = gc_fsa_mark_sweep();
            break;

        case GC_STAGE_PRUNE:
            LOG(TRACE, "GC_STAGE_PRUNE");
            stage = gc_fsa_prune();
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
    return true;
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
    uint_fast32_t sp = gc_thread_info.safe_point_request;
    if (sp & (GC_SAFE_POINT_SCAN_ROOTS|GC_SAFE_POINT_CATCH_UP)) {
        if (gc_fsa() && gc_thread_info.lag_counter > 0) {
            gc_thread_info.lag_counter -= 1;
        } else {
            atomic_fetch_and(&gc_thread_info.safe_point_request, ~GC_SAFE_POINT_CATCH_UP);
        }
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




