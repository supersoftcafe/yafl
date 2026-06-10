
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
// The collector must do GC work at a RATE proportional to the live heap —
// live_pages / GC_PACE_DIV pages of work per page allocated — or a fast
// allocator outruns the marker and a cycle never completes (the heap then
// grows without bound until OOM). But each gc_fsa step must stay SMALL:
// fsa_lock is held for the whole step, and a long hold delays every other
// thread's cycle-start page-take, widening the birth-protection straddle
// window. So rate and batch are decoupled: every step is bounded at
// GC_PACE_STEP_PAGES, and gc_page_alloc schedules the remainder of the rate
// as catch-up steps (lag_counter + GC_SAFE_POINT_CATCH_UP) repaid one bounded
// step per ordinary safe-point.
//
// YAFL_GC_PACE_DIV overrides the divisor: smaller = more GC work per
// allocation = lower memory watermark, higher GC share of CPU.
#define GC_PACE_STEP_PAGES  16    // max pages per gc_fsa step: bounds fsa_lock hold
#define GC_PACE_LAG_MAX     4096  // cap on a thread's accumulated catch-up debt
static unsigned gc_pace_div = 64;

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
static bool gc_poison_enabled = false;
static bool gc_stats_enabled  = false;

static void gc_read_config(void) {
    const char *e;
    if ((e = getenv("YAFL_GC_PACE_DIV")) != NULL) {
        int div = atoi(e);
        if (div > 0) gc_pace_div = (unsigned)div;
    }
    gc_poison_enabled = (e = getenv("YAFL_GC_POISON")) && e[0] && e[0] != '0';
    gc_stats_enabled  = getenv("YAFL_GC_STATS") != NULL;
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
static int_fast32_t gc_catch_up_credit(void);


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

// Mark worklist: objects discovered on ALREADY-PROCESSED pages are queued here
// and scanned directly, instead of re-queueing their whole page and re-diffing
// its bitmaps to find them. Only touched under fsa_lock (the scanner's own
// marking); the mutator-side barrier keeps its reprocess ring. On overflow we
// fall back to the page-requeue path, so this is purely an optimisation.
#define MARK_WORKLIST_SIZE  4096
#define MARK_DRAIN_PER_STEP 512   // bound per-step latency like the page budget
static object_t* mark_worklist[MARK_WORKLIST_SIZE];
static unsigned  mark_worklist_count = 0;


/**
 * Add separate bitmap for atomic marking during early root marking phase.
 * Wipe that bitmap when doing mark-sweep, ready for next iteration.
 */

static list_element_t pages_to_scan  = {&pages_to_scan, &pages_to_scan};
static list_element_t pages_to_prune = {&pages_to_prune, &pages_to_prune};


// --- Idle dwell: how long the collector rests between cycles ----------------
//
// Without a dwell the FSA chains PRUNE -> IDLE -> START on the very next
// allocation, re-marking the whole live heap back-to-back — total GC work
// then scales with cycle frequency rather than with garbage. Instead, after
// each cycle the next one starts only once the allocated page count exceeds
//     min( 3 x survivors of the last cycle's scan set,  total heap / 2 )
// where "survivors" counts pages that came through PRUNE alive (pages
// allocated during the cycle are birth-protected, never enter the prune
// list, and so are deliberately excluded). The half-heap cap means a live
// set approaching half the heap degrades gracefully to continuous
// collection rather than risking OOM. Starts at zero, so the first cycle
// begins with the first page allocation.
extern size_t memory_total_pages(void);
static size_t gc_cycle_survivors  = 0;   // pages surviving PRUNE this cycle
static size_t gc_dwell_threshold  = 0;   // allocated-pages level that starts the next cycle

// --- GC diagnostics (set YAFL_GC_STATS to enable; prints to stderr).
// A sampled progress line every 512 page allocations, plus a [GC TIME]
// summary at exit: time inside gc_fsa per stage vs wall and process CPU.
extern size_t memory_watermark(void);
static _Atomic(uint64_t) gc_stat_mark_steps   = 0;  // gc_fsa_mark_sweep() invocations
static _Atomic(uint64_t) gc_stat_pages_popped = 0;  // pages popped + scanned in mark-sweep
static _Atomic(uint64_t) gc_stat_requeued     = 0;  // page_needs_scan() — re-scan requeues
static _Atomic(uint64_t) gc_stat_rq_mark      = 0;  //   ...from mark_object (synchronous scan mark)
static _Atomic(uint64_t) gc_stat_rq_drain     = 0;  //   ...from post-scan atomic-seen drain
static _Atomic(uint64_t) gc_stat_rq_repro     = 0;  //   ...from reprocess-ring drain
static _Atomic(uint64_t) gc_stat_overflows    = 0;  // reprocess-ring overflow whole-heap rescans
static _Atomic(uint64_t) gc_stat_prune_steps  = 0;  // gc_fsa_prune() invocations
static _Atomic(uint64_t) gc_stat_pages_freed  = 0;  // gc_page_free() calls
static _Atomic(uint64_t) gc_stat_page_allocs  = 0;  // gc_page_alloc() calls
#define GC_STAT_BUMP(c)\
    do { if (UNLIKELY(gc_stats_enabled))\
             atomic_fetch_add_explicit(&(c), 1, memory_order_relaxed);\
    } while (false)

// Nanoseconds spent inside gc_fsa, per stage (index = enum gc_stage). All GC
// work happens there, single-threaded under fsa_lock, so the sum is total
// collector time. Excludes mutator-side barrier checks and allocator memsets.
static _Atomic(uint64_t) gc_stat_stage_ns[8];
static _Atomic(uint64_t) gc_stat_fsa_calls = 0;
static struct timespec   gc_stats_t0;

static void gc_stats_report(void) {
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
}

static void gc_stats_tick(void) {
    if (LIKELY(!gc_stats_enabled)) return;
    uint64_t n = atomic_fetch_add_explicit(&gc_stat_page_allocs, 1, memory_order_relaxed) + 1;
    if ((n & 511) != 0) return;   // sample every 512 page allocations
    fprintf(stderr,
        "[GC] allocs=%llu watermark=%llu live=%llu cycles=%llu stage=%d epoch=%u "
        "mark_steps=%llu popped=%llu requeued=%llu overflows=%llu "
        "rq_mark=%llu rq_drain=%llu rq_repro=%llu prune_steps=%llu freed=%llu\n",
        (unsigned long long)n,
        (unsigned long long)memory_watermark(),
        (unsigned long long)memory_count(),
        (unsigned long long)atomic_load(&gc_cycle_count),
        (int)stage, (unsigned)epoch,
        (unsigned long long)atomic_load(&gc_stat_mark_steps),
        (unsigned long long)atomic_load(&gc_stat_pages_popped),
        (unsigned long long)atomic_load(&gc_stat_requeued),
        (unsigned long long)atomic_load(&gc_stat_overflows),
        (unsigned long long)atomic_load(&gc_stat_rq_mark),
        (unsigned long long)atomic_load(&gc_stat_rq_drain),
        (unsigned long long)atomic_load(&gc_stat_rq_repro),
        (unsigned long long)atomic_load(&gc_stat_prune_steps),
        (unsigned long long)atomic_load(&gc_stat_pages_freed));
}


// DEBUG: when set, allocation does NOT drive the GC FSA, so a test can step the
// collector by hand (gc_debug_step) and pin down exact interleavings.
EXPORT bool gc_debug_manual_mode = false;

static NOINLINE_DEBUG gc_page_t* gc_page_alloc(unsigned page_count) {
    gc_stats_tick();
    if (!gc_debug_manual_mode) {
        // One bounded GC step now, plus schedule the rest of the adaptive
        // rate as catch-up steps repaid one per safe-point. Cap the
        // accumulated debt so a brief allocation burst cannot build a backlog
        // that stalls the thread at its next safe-points.
        int_fast32_t lag = gc_catch_up_credit();
        if (!gc_fsa()) lag += 1;   // missed fsa_lock: repay this step as well
        if (lag > 0) {
            gc_thread_info.lag_counter += lag;
            if (gc_thread_info.lag_counter > GC_PACE_LAG_MAX)
                gc_thread_info.lag_counter = GC_PACE_LAG_MAX;
            atomic_fetch_or(&gc_thread_info.safe_point_request, GC_SAFE_POINT_CATCH_UP);
        }
    }

    // memory_pages_alloc guarantees zeroed pages (virgin mmap pages are zero
    // already; reused runs are zeroed on the reuse path), so the header
    // bitmaps, the slot region and every future object's fields start NULL
    // without any per-page or per-object memset here.
    gc_page_t *page = memory_pages_alloc(page_count);
    page->head.pages = page_count;
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

static NOINLINE_DEBUG void *_object_alloc(size_t size, bool is_mutable) {
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
    // Every field is already zero: pages arrive zeroed from memory_pages_alloc
    // and each slot is bumped at most once per page lifetime. That NULL state
    // is load-bearing — the generated code writes each pointer field through
    // the GC write barrier, which marks the field's PRIOR value, and a
    // partially-initialised object may be scanned; NULL is safe, garbage is not.
    object->vtable = vtable;
    LOG(ULTRA, "ALLOC(0x%lx) -> %s", (uintptr_t)object, vtable->name);
    return object;
}

EXPORT void* array_create(vtable_t *vtable, int32_t length) {
    assert(length >= 0);
    assert(vtable->array_el_size != 0);
    size_t total = vtable->object_size + (size_t)vtable->array_el_size * (size_t)length;
    object_t *object = _object_alloc(total, vtable->is_mutable);
    // The whole object is already zero (pages arrive zeroed from
    // memory_pages_alloc; slots are bumped at most once per page lifetime).
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

// Any thread that can do allocation must call this early on
EXPORT void gc_declare_thread(thread_roots_declaration_func_t thread_roots_declaration_func, void*thread_roots_context) {
    yafl_stack_guard_init();   // turn a stack overflow on this thread into a clean error
    object_t* some_random_var = NULL;
#ifdef STACK_GROWS_DOWN
    gc_thread_info.stack_upper_ptr = &some_random_var;
#else
    gc_thread_info.stack_lower_ptr = &some_random_var;
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

    // Copy each object to newly allocated space
    page->head.compacted = true;
    for (unsigned index = 0; index < object_count; ++index) {
        object_t *object = (object_t*)&page->slots[objects[index].o];
        size_t      size = objects[index].s;

        object_t *target = _object_alloc(size, false);       // Allocate new object
        memcpy(target, object, size);                        // Copy contents across
        object->vtable = (vtable_t*)target;                  // Forwarding pointer: a heap
                                                             // address here means "moved"
    }
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

    gc_cycle_survivors = 0;   // accumulated through this cycle's PRUNE stage
    mark_worklist_count = 0;  // stale entries must not leak across cycles

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
            page->head.scanner.pinned = true;
            atomic_bitmap_fetch_set(&page->head.scanner.atomic_seen, slot);
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

    assert(!list_empty(&pages_to_scan));
    assert(list_empty(&pages_to_prune));

    return GC_STAGE_MARK_SWEEP;
}




// How many catch-up steps to credit per page allocation so the total rate is
// ~live_pages/gc_pace_div pages of GC work per page allocated. Each step
// processes up to GC_PACE_STEP_PAGES pages, and gc_page_alloc itself drives
// one step, so schedule the remainder onto the thread's safe-points via
// lag_counter. See the pacing comment at the top of this file.
static int_fast32_t gc_catch_up_credit(void) {
    // No catch-up debt while the collector is dwelling between cycles — the
    // racy read of `stage` is fine (advisory; a cycle starting concurrently
    // just means this allocation credits nothing and the next one credits).
    if (stage == GC_STAGE_IDLE)
        return 0;
    size_t rate  = memory_count() / gc_pace_div;
    size_t steps = rate / GC_PACE_STEP_PAGES;
    if (steps > GC_PACE_LAG_MAX) steps = GC_PACE_LAG_MAX;
    return steps > 0 ? (int_fast32_t)(steps - 1) : 0;
}

static void gc_fsa_mark_sweep$page_needs_scan(gc_page_t *page) {
    GC_STAT_BUMP(gc_stat_requeued);
    page->head.scanner.processed_by_epoch = 0;
    list_unlink((list_element_t*)&page->head.list);
    list_link(&pages_to_scan, (list_element_t*)&page->head.list);
}

static void gc_fsa_mark_sweep$mark_object(object_t *object) {
    // Mark the target object
    gc_page_t *page; ptrdiff_t slot;
    object_get_page_and_slot(object, &page, &slot);
    bool was_set = bitmap_fetch_set(&page->head.scanner.seen, slot);

    // Newly marked on a page the scanner already processed this epoch: queue
    // the OBJECT for a direct scan; re-queue the whole page only if the
    // worklist is full.
    if (!was_set && page->head.scanner.processed_by_epoch == epoch) {
        if (mark_worklist_count < MARK_WORKLIST_SIZE) {
            mark_worklist[mark_worklist_count++] = object;
        } else {
            GC_STAT_BUMP(gc_stat_rq_mark);
            gc_fsa_mark_sweep$page_needs_scan(page);
        }
    }
}

static void gc_fsa_mark_sweep$scan_elements(object_t **base_ptr, ptr_mask_t pointer_locations) {
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

            *ptr_ptr = object = (object_t*)vt;
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
    if (UNLIKELY(gc_poison_enabled))
        _dbg_dangle_check(object);
    // Find the real vtable pointer (forwarding-aware; targets get marked too)
    vtable_t *vt = object->vtable;
    for (object_t *ptr = object; UNLIKELY(vtable_is_forward(vt)); ) {
        ptr = (object_t*)vt;
        gc_fsa_mark_sweep$mark_object(ptr);
        vt = ptr->vtable;
    }

    // Scan references
    if (vt->object_pointer_locations) {
        gc_fsa_mark_sweep$scan_elements((object_t**)object, vt->object_pointer_locations);
    }

    if (vt->array_el_pointer_locations) {
        uint32_t len = *(uint32_t*)&((char*)object)[vt->array_len_offset];
        char*  array = ((char*)object) + vt->object_size;
        for (; len-- > 0; array += vt->array_el_size) {
            gc_fsa_mark_sweep$scan_elements((object_t**)array, vt->array_el_pointer_locations);
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

static NOINLINE_DEBUG enum gc_stage gc_fsa_mark_sweep() {
    // size_t page_count = 0;
    // for (list_element_t *pp = pages_to_scan.next; pp != &pages_to_scan; pp = pp->next)
    //     page_count++;
    //
    // size_t x = page_count;

    GC_STAT_BUMP(gc_stat_mark_steps);

    // Drain the mark worklist first: scan queued objects directly (LIFO, so
    // chains are followed depth-first while hot). Mark their scanned bit so a
    // later pop of their page skips them in the seen&~scanned diff. Bounded
    // per step to keep fsa_lock hold times short; scanning may push more.
    for (unsigned drained = 0;
         mark_worklist_count > 0 && drained < MARK_DRAIN_PER_STEP; ++drained) {
        object_t *object = mark_worklist[--mark_worklist_count];
        gc_page_t *pg; ptrdiff_t sl;
        object_get_page_and_slot(object, &pg, &sl);
        bitmap_fetch_set(&pg->head.scanner.scanned, sl);
        gc_fsa_mark_sweep$scan_object(object);
    }

    for (unsigned count = 0; count < GC_PACE_STEP_PAGES; ++count) {
        gc_page_t *page = (gc_page_t*)list_pop(&pages_to_scan);
        if (page == NULL) break;
        GC_STAT_BUMP(gc_stat_pages_popped);
        assert(page->head.scanner.processed_by_epoch != epoch);

        if (bitmap_or_test_reset_all(&page->head.scanner.seen, &page->head.scanner.atomic_seen))
            while (gc_fsa_mark_sweep$scan_page(page));

        page->head.scanner.processed_by_epoch = epoch;
        list_link(&pages_to_prune, (list_element_t*)&page->head.list);

        // Drain marks that landed between the atomic_exchanges above and
        // processed_by_epoch being set. Those barriers saw epoch mismatch
        // and didn't enqueue for reprocessing. Any marks after epoch is set
        // go through the normal reprocess pipeline.
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

    // More work needs to happen
    if (!list_empty(&pages_to_scan) || mark_worklist_count > 0) {
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





static NOINLINE_DEBUG enum gc_stage gc_fsa_prune() {
    GC_STAT_BUMP(gc_stat_prune_steps);
    for (unsigned count = 0; count < GC_PACE_STEP_PAGES; ++count) {
        gc_page_t *page = (gc_page_t*)list_pop(&pages_to_prune);
        if (page == NULL) break;
        assert(page->head.scanner.processed_by_epoch == epoch);

        if (bitmap_test_all(&page->head.scanner.seen)) {
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
            gc_cycle_survivors += page->head.pages;
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
        } else {
            assert(bitmap_test_all(&page->head.scanner.atomic_seen) == false);
            gc_page_free(page);
        }
    }

    if (list_empty(&pages_to_prune)) {
        // Set the dwell for the next cycle: rest until the allocated page
        // count exceeds 3x this cycle's survivors, capped at half the heap
        // (see the idle-dwell comment near the top of this file).
        size_t cap = memory_total_pages() / 2;
        size_t threshold = gc_cycle_survivors * 3;
        gc_dwell_threshold = (cap != 0 && threshold > cap) ? cap : threshold;

        // End of a full GC cycle.
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
            // Idle dwell: rest until allocation crosses the threshold set at
            // the end of the previous cycle. Driven by gc_page_alloc, so the
            // check runs once per page allocated — not per safe-point.
            if (memory_count() > gc_dwell_threshold) {
                LOG(TRACE, "GC_STAGE_IDLE");
                stage = GC_STAGE_START;
            }
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
        uint64_t ns = (uint64_t)(t_out.tv_sec - t_in.tv_sec) * 1000000000ull
                    + (uint64_t)(t_out.tv_nsec - t_in.tv_nsec);
        atomic_fetch_add_explicit(&gc_stat_stage_ns[entry_stage], ns, memory_order_relaxed);
        atomic_fetch_add_explicit(&gc_stat_fsa_calls, 1, memory_order_relaxed);
    }

    atomic_store(&fsa_lock, false);
    return true;
}


// DEBUG: drive the GC FSA one stage at a time, and read its state, so a test can
// reproduce an exact interleaving deterministically.
EXPORT int  gc_debug_stage(void) { return (int)stage; }
EXPORT void gc_debug_step(void)  { gc_fsa(); }

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




