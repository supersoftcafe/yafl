
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
static _Atomic(size_t)  upper_watermark = 0;    // Highest page index ever part of an allocation
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
static size_t scan_runs_topdown(size_t snapshot, size_t page_count, size_t step_budget) {
    if (snapshot < page_count)
        return SIZE_MAX;

    size_t top = snapshot - page_count;          // highest legal window start
    size_t i = top;

    size_t steps_remaining = snapshot < step_budget ? snapshot : step_budget;
    size_t lap_remaining = snapshot;   // hard bound: one full lap, free skips included
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
                if (i < page_count) break;   // bottom reached: nothing warm fits
                i -= page_count;
                continue;
            }
            if (try_claim_run(i, page_count))
                return i;
            // Lost the race for this window; nudge downward and try again.
            steps_remaining -= 1;
            lap_remaining -= 1;
            if (i == 0) break;               // bottom reached
            i -= 1;
            continue;
        }

        size_t obstruction = i + j - 1;
        size_t probed = page_count - j + 1;
        steps_remaining = sat_sub(steps_remaining, probed);
        lap_remaining   = sat_sub(lap_remaining, probed);
        if (obstruction < page_count)
            break;                           // no window fits below the obstruction
        i = obstruction - page_count;
    }

    if (fallback != SIZE_MAX && try_claim_run(fallback, page_count))
        return fallback;
    return SIZE_MAX;
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
static void* claimed_run(size_t idx, size_t page_count) {
    atomic_fetch_add_explicit(&alloc_count, page_count, memory_order_relaxed);
    atomic_fetch_add_explicit(&pages_ever, page_count, memory_order_relaxed);
    for (size_t j = 0; j < page_count; ++j) {
        if (atomic_exchange_explicit(&pages_cold[idx + j], 0, memory_order_relaxed)) {
            atomic_fetch_sub_explicit(&cold_count, 1, memory_order_relaxed);
            atomic_fetch_add_explicit(&scavenge_reclaimed, 1, memory_order_relaxed);
            if (page_count > 1)
                atomic_fetch_add_explicit(&scavenge_reclaimed_runs, 1, memory_order_relaxed);
        }
    }
    return pages_heap + idx * GC_PAGE_SIZE;
}

EXPORT void* memory_pages_alloc(size_t page_count) {
    assert(page_count > 0);

    // pthread_once' own fast path is a single relaxed load; an outer
    // pages_heap-NULL check would race with the non-atomic write inside init().
    pthread_once(&pages_once, init);

    // New scavenge epoch: reset both cursors (see epoch_seen). The first
    // allocation of the epoch pays one long scan over the dense prefix;
    // everything after continues next-fit from the frontier it found.
    uint8_t epoch = scavenge_epoch_now();
    if (UNLIKELY(epoch != epoch_seen)) {
        epoch_seen = epoch;
        alloc_cursor = 0;
    }

    while (true) {
        // Phase 1: reuse free pages within the existing active region.
        // Singles scan bottom-up, runs top-down (see scan_runs_topdown).
        size_t snapshot = atomic_load_explicit(&upper_watermark, memory_order_relaxed);
        size_t idx = page_count == 1
            ? scan_within(snapshot, 1, MAX_SCAN_PROBES, false)
            : scan_runs_topdown(snapshot, page_count, MAX_SCAN_PROBES);
        if (idx != SIZE_MAX) {
            return claimed_run(idx, page_count);
        }

        // Phase 2: no reusable run inside the probe budget; extend the active
        // region. CAS-loop bounds growth to total_page_count without
        // overshooting and never advances past the heap end even under
        // concurrent bumps.
        size_t cur = snapshot;
        size_t end;
        while (true) {
            // Overflow-safe bounds check: `cur + page_count` could wrap if a
            // caller asked for a pathological page_count.
            if (page_count > total_page_count - cur) {
                // The heap is too full to bump. The bounded Phase-1 scan may
                // have missed a usable hole further along, so do a last-ditch
                // unbounded scan before declaring OOM.
                size_t last = scan_within(cur, page_count, SIZE_MAX, true);
                if (last != SIZE_MAX) {
                    return claimed_run(last, page_count);
                }
                abort_on_out_of_memory();
            }
            end = cur + page_count;
            if (atomic_compare_exchange_weak_explicit(
                    &upper_watermark, &cur, end,
                    memory_order_acq_rel, memory_order_relaxed))
                break;
        }

        if (try_claim_run(cur, page_count)) {
            // Deliberately do not move alloc_cursor here. scan_within parked
            // it just past where it gave up; preserving that lets the next
            // allocation resume the walk and find any free region further
            // along, instead of redoing the same fruitless probes from the
            // bump location.
            return claimed_run(cur, page_count);
        }
        // A concurrent scanner that observed our new watermark snuck in and
        // claimed the freshly exposed pages first. The watermark advance is
        // not wasted — those pages now belong to whoever claimed them — so
        // loop and re-enter Phase 1 against the larger region.
    }
}

EXPORT void memory_pages_free(void* ptr, size_t page_count) {
    assert(page_count > 0);
    assert(memory_pages_is_alloc_head(ptr));
    assert(((uintptr_t)ptr & (GC_PAGE_SIZE-1)) == 0);

    ptrdiff_t offset = ((char*)ptr - pages_heap) / GC_PAGE_SIZE;
    size_t watermark = atomic_load_explicit(&upper_watermark, memory_order_relaxed);
    assert((size_t)(offset + page_count) <= watermark);

    // Caller claimed `page_count` pages. The page immediately following the
    // run must be either HEAD (next allocation), FREE, or past the watermark.
    // Anything else means the caller has truncated a multi-page allocation
    // and would leave dangling BODY markers no scanner could ever reclaim.
    if ((size_t)(offset + page_count) < watermark) {
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
        atomic_store_explicit(&pages_info[offset + index], PAGE_MARKER_FREE, memory_order_release);
    }

    atomic_fetch_sub_explicit(&alloc_count, page_count, memory_order_relaxed);
}

EXPORT bool memory_pages_is_alloc_head(void* ptr) {
    ptrdiff_t offset = ((char*)ptr - pages_heap) / GC_PAGE_SIZE;
    return offset >= 0
        && (size_t)offset < atomic_load_explicit(&upper_watermark, memory_order_relaxed)
        && atomic_load_explicit(&pages_info[offset], memory_order_relaxed) == PAGE_MARKER_HEAD;
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
    if (end - lo < SCAVENGE_MIN_SPAN) {
        uint8_t now = scavenge_epoch_now();
        for (size_t k = lo; k < end; ++k) {
            atomic_store_explicit(&pages_free_epoch[k], now, memory_order_relaxed);
            atomic_store_explicit(&pages_info[k], PAGE_MARKER_FREE, memory_order_release);
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
    if (watermark == 0)
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
    size_t warm_free = sat_sub(watermark, used + cold);
    if (warm_free <= retain + SCAVENGE_HYSTERESIS)
        return;
    size_t quota = warm_free - retain;
    if (quota > max_pages)
        quota = max_pages;

    // Resume where the previous call stopped. Both 0 (bottom reached) and
    // anything beyond the watermark (first call, or the watermark moved)
    // mean "start a fresh pass from the top".
    size_t i = scavenge_cursor;
    if (i == 0 || i > watermark)
        i = watermark;

    size_t scanned = 0;            // bounds the walk to one full lap
    size_t run_lo = 0, run_end = 0; // pending claimed run, growing downward
    while (quota > 0 && scanned < watermark) {
        if (i == 0) {
            scavenge_release(run_lo, run_end);
            run_lo = run_end = 0;
            i = watermark;
            continue;   // wrap is free, like the allocation scans
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

// Capacity of the whole managed heap in pages (YAFL_HEAP_SIZE / GC_PAGE_SIZE).
// Zero until the first allocation initialises the heap.
EXPORT size_t memory_total_pages() {
    return total_page_count;
}


