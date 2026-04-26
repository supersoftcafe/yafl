
#define OBJECT_HEADER_EXCLUSIONS

#include "yafl.h"
#include <malloc.h>
#include <setjmp.h>


#define COMPACT_THRESHOLD_PERCENT   33
#define PAGES_SCANNED_PER_ALLOC     2
#define PAGES_PRUNED_PER_ALLOC      16
#define REPROCESS_PAGE_COUNT        16
#define MMAP_RELEASE_PAGE_MASK      0x3f
#undef  CLEAR_RELEASED_HEAP


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
        uint32_t processed_by_epoch; // Scanned has processed this page..  Reset to false when something changes
        bool          pinned; // Stack references found, which can't be re-written easily
    } scanner;

    bitmap_t objects; // Starting slot of each known object
    uint32_t     tag; // Safety check
    uint16_t   pages; // Number of pages, including this one, in the complete allocation
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



static unsigned bitmap_count(const bitmap_t *bitmap) {
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
        result |= (target->a[index] |= source->a[index]);
        source->a[index] = 0;
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

    struct gc_thread_info *next;

    thread_roots_declaration_func_t thread_roots_declaration_func;
    void* thread_roots_context;

    bool roots_scanned;
    _Atomic(enum thread_state) thread_state;

    list_element_t free_pages;
    unsigned free_pages_counter;

    // Quarantine: pages freed during a GC cycle are not reusable in the same
    // cycle (the scanner may still hold a stale pointer through a forwarding
    // chain, or a conservative stack pointer might still resolve to a slot in
    // them). Pages are aged through pending_free_pages_curr → ..._prev → free
    // across cycle boundaries; they spend at least one full cycle in pending.
    list_element_t pending_free_pages_curr;
    list_element_t pending_free_pages_prev;
    uint64_t       last_drained_cycle;

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
// GC cycle has completed). Per-thread allocation paths consult this to age
// quarantined free pages: a page freed when this counter == K only becomes
// reusable when the counter has advanced past K.
static _Atomic(uint64_t)     gc_cycle_count = 0;

static _Atomic(gc_page_t*) reprocess_page_list[REPROCESS_PAGE_COUNT];
static atomic_size_t       reprocess_page_head;
static atomic_size_t       reprocess_page_tail;
static atomic_bool         reprocess_overflow_flag;


/**
 * Add separate bitmap for atomic marking during early root marking phase.
 * Wipe that bitmap when doing mark-sweep, ready for next iteration.
 */

static list_element_t pages_to_scan  = {&pages_to_scan, &pages_to_scan};
static list_element_t pages_to_prune = {&pages_to_prune, &pages_to_prune};



static NOINLINE_DEBUG gc_page_t* gc_page_alloc(unsigned page_count) {
    if (!gc_fsa()) {
        gc_thread_info.lag_counter += 1;
        atomic_fetch_or(&gc_thread_info.safe_point_request, GC_SAFE_POINT_CATCH_UP);
    }

    // Age quarantined pages whenever the GC has advanced past the cycle in
    // which we last drained: the prev list is now ripe (it survived a full
    // cycle in pending), so move it to free; promote curr → prev. A page
    // freed during cycle K therefore becomes reusable no earlier than cycle
    // K+2, which is always after any scanner active at the time of the free
    // has finished.
    {
        uint64_t cur = atomic_load(&gc_cycle_count);
        if (cur != gc_thread_info.last_drained_cycle) {
            list_move(&gc_thread_info.free_pages, &gc_thread_info.pending_free_pages_prev);
            list_move(&gc_thread_info.pending_free_pages_prev, &gc_thread_info.pending_free_pages_curr);
            gc_thread_info.last_drained_cycle = cur;
        }
    }

    gc_page_t *page = list_pop(&gc_thread_info.free_pages) ?: memory_pages_alloc(page_count);

    memset(page, 0, GC_PAGE_SIZE * page_count);
    page->head.pages = page_count;
    page->head.tag = PAGE_MAGIC_NUMBER;

    LOG(TRACE, "gc_page_alloc(%d) = 0x%lx", page_count, (uintptr_t)page);

    return page;
}

static NOINLINE_DEBUG void gc_page_free(gc_page_t* page) {
    assert(page->head.tag == PAGE_MAGIC_NUMBER);
    LOG(TRACE, "gc_page_free(%d) = 0x%lx", page->head.pages, (uintptr_t)page);

    // Multi-page allocations and the every-Nth single-page release path go
    // back to the OS immediately. They cannot be inspected by a stale pointer
    // post-munmap (the read would segfault), so quarantining them buys
    // nothing.
    if (page->head.pages != 1 || (++gc_thread_info.free_pages_counter & MMAP_RELEASE_PAGE_MASK) == 0) {
        page->head.tag = 0;
        memory_pages_free(page, page->head.pages);
        return;
    }

    // Single-page release that stays in process memory. Park on the per-thread
    // quarantine list. Leave page->head.tag == PAGE_MAGIC_NUMBER and the
    // objects bitmap intact for the duration of the quarantine, so any
    // conservative pointer that still resolves to this page passes the
    // existing on-heap checks rather than tripping an assertion. The page
    // becomes reusable only after gc_page_alloc ages it through curr → prev →
    // free in a future GC cycle.
    list_link(&gc_thread_info.pending_free_pages_curr, (list_element_t*)&page->head.list);
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
        // size_t page_count = (sizeof(gc_page_head_t) + actual_size + GC_PAGE_SIZE - 1) / GC_PAGE_SIZE;
        // gc_page_t* page = _gc_page_alloc(page_count);
        // page->head.object_heads.a[0] = 1;
        // return page->slots;
        abort_on_too_large_object();
    }

    bump_pointers_t *bp = is_mutable
        ? &gc_thread_info.region_mutable
        : &gc_thread_info.region_immutable;

    if (UNLIKELY(bp->bump - bp->base < actual_size)) {
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

    return object;
}

EXPORT void* object_create(vtable_t *vtable) {
    assert(vtable->array_el_size == 0);
    object_t *object = _object_alloc(vtable->object_size, vtable->is_mutable);
    object->vtable = VT_TAG_SET(vtable, VT_TAG_MANAGED);
    LOG(ULTRA, "ALLOC(0x%lx) -> %s", (uintptr_t)object, vtable->name);
    return object;
}

EXPORT void* array_create(vtable_t *vtable, int32_t length) {
    assert(length >= 0);
    assert(vtable->array_el_size != 0);
    object_t *object = _object_alloc(vtable->object_size + vtable->array_el_size*length, vtable->is_mutable);
    object->vtable = VT_TAG_SET(vtable, VT_TAG_MANAGED);
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
    while (UNLIKELY(VT_TAG_GET(vt) == VT_TAG_FORWARD)) {
        object_t *next_object = (object_t*)VT_TAG_UNSET(vt);
        vt = next_object->vtable;
    }
    return VT_TAG_UNSET(vt);
}

EXPORT fun_t object_lookup_vtable(object_t *object, intptr_t id) {
    vtable_t* vtable = object_get_vtable(object);
    intptr_t index = id & vtable->functions_mask;
    vtable_entry_t* entry = (vtable_entry_t*)(((char*)&(vtable->lookup[-1])) + index);
    do {entry++;
        // It's important that we use signed arithmatic here.
        // Blank entries have -1 as the id, which will cause this
        //    loop to exit and call the abort function (from the vtable)
        //    It's a safety feature that costs us nothing.
    } while ((entry->i ^ id) > 0);
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
        assert(gc_thread_info.thread_state == THREAD_STATE_SUSPENDED || gc_thread_info.thread_state == THREAD_STATE_SUSPENDED_SCAN);
    } while (!gc_change_thread_state(&gc_thread_info, THREAD_STATE_SUSPENDED, THREAD_STATE_RUNNING));
}

// Any thread that can do allocation must call this early on
EXPORT void gc_declare_thread(thread_roots_declaration_func_t thread_roots_declaration_func, void*thread_roots_context) {
    object_t* some_random_var = NULL;
#ifdef STACK_GROWS_DOWN
    gc_thread_info.stack_upper_ptr = &some_random_var;
#else
    gc_thread_info.stack_lower_ptr = &some_random_var;
#endif

    gc_thread_info.thread_roots_declaration_func = thread_roots_declaration_func;
    gc_thread_info.thread_roots_context = thread_roots_context;

    gc_thread_info.free_pages.next = gc_thread_info.free_pages.prev = &gc_thread_info.free_pages;
    gc_thread_info.pending_free_pages_curr.next = gc_thread_info.pending_free_pages_curr.prev = &gc_thread_info.pending_free_pages_curr;
    gc_thread_info.pending_free_pages_prev.next = gc_thread_info.pending_free_pages_prev.prev = &gc_thread_info.pending_free_pages_prev;
    gc_thread_info.last_drained_cycle = 0;

    gc_thread_info.next = threads;
    gc_thread_info.thread_state = THREAD_STATE_RUNNING;

    gc_thread_info.new_pages.next = &gc_thread_info.new_pages;
    gc_thread_info.new_pages.prev = &gc_thread_info.new_pages;

    while (!atomic_compare_exchange_weak(&threads, &gc_thread_info.next, &gc_thread_info));
}

static NOINLINE_DEBUG void gc_compact_page(gc_page_t *page) {
    const unsigned slots_threshold = SLOTS_PER_PAGE * COMPACT_THRESHOLD_PERCENT / 100;

    // Previously compacted. If we do it again we'll be making redundent copies.
    if (page->head.compacted)
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
        object->vtable = VT_TAG_SET(target, VT_TAG_FORWARD); // Set forwarding pointer
    }
}








static bool gc_object_is_on_heap_slow(object_t *object) {
    uintptr_t asint = (uintptr_t)object;
    gc_page_t *page = (gc_page_t*)(asint &~ (GC_PAGE_SIZE-1));
    return object != NULL                     // Must have a non-zero value
        && (asint & (GC_SLOT_SIZE-1)) == 0    // Pointer aligns with slot boundaries
        && memory_pages_is_heap(object)       // Pointer lands on a real page on managed heap
        && (asint & (GC_PAGE_SIZE-1)) >= offsetof(gc_page_t, slots)             // Does NOT point into the page header
        && bitmap_test(&page->head.objects, ((slot_t*)object) - page->slots)    // Is a real and exists object in this page
        && VT_TAG_GET(object->vtable) != VT_TAG_UNMANAGED;     // Must be heap managed according to the tag
}

static bool gc_object_is_on_heap_fast(object_t *object) {
    return object != NULL                                  // Must have a non-zero value
        && ((intptr_t)object & 3) == 0                     // No packed data as they aren't real pointers
        && VT_TAG_GET(object->vtable) != VT_TAG_UNMANAGED; // Must be heap managed according to the tag
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

static void gc_object_mark_as_seen(object_t *object) {
    gc_page_t* page; ptrdiff_t slot;
    object_get_page_and_slot(object, &page, &slot);
    bitmap_fetch_set(&page->head.scanner.seen, slot);

    vtable_t *vt = object_get_vtable(object);
    assert(vt != NULL);
    LOG(ULTRA, "MARK(0x%lx) -> %s", (uintptr_t)object, vt->name);
}

static NOINLINE_DEBUG void atomic_gc_object_seen_by_field(object_t **field_ptr) {
    object_t *object = *field_ptr;
    while (gc_object_is_on_heap_fast(object)) {
        atomic_gc_object_mark_as_seen(object);
        if (LIKELY(VT_TAG_GET(object->vtable) != VT_TAG_FORWARD)) break;
        *field_ptr = object = (object_t*)VT_TAG_UNSET(object->vtable);
    }
}






static NOINLINE_DEBUG enum gc_stage gc_fsa_start() {
    if (++epoch == 0)
        epoch = 1;

    gc_write_barrier_requested = true;
    reprocess_page_head = reprocess_page_tail = 0;
    memset(reprocess_page_list, 0, sizeof(reprocess_page_list));

    declare_roots_yafl(atomic_gc_object_seen_by_field);
    declare_roots_thread(atomic_gc_object_seen_by_field);
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

            gc_page_t* page; ptrdiff_t slot;
            object_get_page_and_slot(object, &page, &slot);
            page->head.scanner.pinned = true;

            atomic_gc_object_mark_as_seen(object);
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
        // Grab some pages
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

    assert(!list_empty(&pages_to_scan));
    assert(list_empty(&pages_to_prune));

    return GC_STAGE_MARK_SWEEP;
}




static void gc_fsa_mark_sweep$page_needs_scan(gc_page_t *page) {
    page->head.scanner.processed_by_epoch = 0;
    list_unlink((list_element_t*)&page->head.list);
    list_link(&pages_to_scan, (list_element_t*)&page->head.list);
}

static void gc_fsa_mark_sweep$mark_object(object_t *object) {
    // Mark the target object
    gc_page_t *page; ptrdiff_t slot;
    object_get_page_and_slot(object, &page, &slot);
    bool was_set = bitmap_fetch_set(&page->head.scanner.seen, slot);

    // Might need to move page ahead of the scanner for a re-scan
    if (!was_set && page->head.scanner.processed_by_epoch == epoch)
        gc_fsa_mark_sweep$page_needs_scan(page);
}

static void gc_fsa_mark_sweep$scan_elements(object_t **base_ptr, uint64_t pointer_locations) {
    while (pointer_locations) {
        // Get the object reference
        unsigned index = __builtin_ctzll(pointer_locations);
        pointer_locations &= pointer_locations - 1;
        object_t **ptr_ptr = &base_ptr[index];
        object_t *object = *ptr_ptr;

        while (gc_object_is_on_heap_fast(object)) {
            gc_fsa_mark_sweep$mark_object(object);

            // Apply any forwarding pointer if found
            vtable_t *vt = object->vtable;
            if (LIKELY(VT_TAG_GET(vt) != VT_TAG_FORWARD))
                break;

            *ptr_ptr = object = (object_t*)VT_TAG_UNSET(vt);
            vt = object->vtable;
        }
    }
}

static void gc_fsa_mark_sweep$scan_object(object_t *object) {
    // Find the real vtable pointer
    vtable_t *vt = object->vtable;
    for (object_t *ptr = object; UNLIKELY(VT_TAG_GET(vt) == VT_TAG_FORWARD); ) {
        ptr = (object_t*)VT_TAG_UNSET(vt);
        gc_fsa_mark_sweep$mark_object(ptr);
        vt = ptr->vtable;
    }
    vt = VT_TAG_UNSET(vt);

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

    for (unsigned count = 0; count < PAGES_SCANNED_PER_ALLOC; ++count) {
        gc_page_t *page = (gc_page_t*)list_pop(&pages_to_scan);
        if (page == NULL) break;
        assert(page->head.scanner.processed_by_epoch != epoch);

        if (bitmap_or_test_reset_all(&page->head.scanner.seen, &page->head.scanner.atomic_seen))
            while (gc_fsa_mark_sweep$scan_page(page));

        page->head.scanner.processed_by_epoch = epoch;
        list_link(&pages_to_prune, (list_element_t*)&page->head.list);
    }

    // Move re-process pages back on to the scan list
    while (reprocess_page_head < reprocess_page_tail) {
        size_t index = atomic_fetch_add(&reprocess_page_head, 1);
        gc_page_t *page;
        do {page = atomic_exchange(&reprocess_page_list[index % REPROCESS_PAGE_COUNT], NULL);
        } while (page == NULL);
        gc_fsa_mark_sweep$page_needs_scan(page);
    }

    // More work needs to happen
    if (!list_empty(&pages_to_scan)) {
        return GC_STAGE_MARK_SWEEP;
    }

    // Lots of pages need to be re-processed
    bool rp_flag = atomic_exchange(&reprocess_overflow_flag, false);
    if (rp_flag) {
        memset(reprocess_page_list, 0, sizeof(reprocess_page_list));
        reprocess_page_head = reprocess_page_tail = 0;
        list_move(&pages_to_scan, &pages_to_prune);
        epoch = epoch==-1 ? 1 : epoch+1;
        return GC_STAGE_MARK_SWEEP;
    }

    // All done
    gc_write_barrier_requested = false;
    return GC_STAGE_PRUNE;
}





static NOINLINE_DEBUG enum gc_stage gc_fsa_prune() {
    for (unsigned count = 0; count < PAGES_PRUNED_PER_ALLOC; ++count) {
        gc_page_t *page = (gc_page_t*)list_pop(&pages_to_prune);
        if (page == NULL) break;
        assert(page->head.scanner.processed_by_epoch == epoch);

        if (bitmap_test_all(&page->head.scanner.seen)) {
#ifdef CLEAR_RELEASED_HEAP
            for (unsigned index = 0; index < sizeof(bitmap_t) / sizeof(mask_bits_t); ++index) {
                mask_bits_t value = page->head.objects.a[index] &~ page->head.scanner.seen.a[index];
                unsigned offset = index * GC_MASK_SIZE;
                while (value) {
                    unsigned slot = __builtin_ctzll(value) + offset;
                    value &= value-1;
                    object_t *object = (object_t*)&page->slots[slot];
                    LOG(ULTRA, "RELEASE(0x%lx) -> %s", (uintptr_t)object, object_get_vtable(object)->name);
                    size_t size = object_get_size(object);
                    memset(object, 0x42, size);
                }
            }
#endif
            page->head.objects = page->head.scanner.seen;
            bitmap_reset_all(&page->head.scanner.seen);
            bitmap_reset_all(&page->head.scanner.scanned);
            bitmap_reset_all(&page->head.scanner.atomic_seen);
            list_unlink((list_element_t*)&page->head.list);
            list_link(&pages_to_scan, (list_element_t*)&page->head.list);
#if COMPACT_THRESHOLD_PERCENT > 0
            gc_compact_page(page);
#endif
        } else {
            assert(bitmap_test_all(&page->head.scanner.atomic_seen) == false);
            gc_page_free(page);
        }
    }

    if (list_empty(&pages_to_prune)) {
        // End of a full GC cycle: pages quarantined during this cycle now
        // age one step toward reuse. Other threads observe this bump on
        // their next gc_page_alloc and drain their own pending lists.
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

    switch (stage) {
        case GC_STAGE_NOT_STARTED:
            stage = GC_STAGE_NOT_STARTED;
            atomic_store(&fsa_lock, false);
            return true;

        case GC_STAGE_IDLE:
            LOG(TRACE, "GC_STAGE_IDLE");
            stage = GC_STAGE_START;
            atomic_store(&fsa_lock, false);
            return true;

        case GC_STAGE_START:
            LOG(TRACE, "GC_STAGE_START");
            stage = gc_fsa_start();
            atomic_store(&fsa_lock, false);
            return true;

        case GC_STAGE_SCAN_ROOTS:
            LOG(TRACE, "GC_STAGE_SCAN_ROOTS");
            stage = gc_fsa_scan_roots();
            atomic_store(&fsa_lock, false);
            return true;

        case GC_STAGE_MARK_SWEEP:
            LOG(TRACE, "GC_STAGE_MARK_SWEEP");
            stage = gc_fsa_mark_sweep();
            atomic_store(&fsa_lock, false);
            return true;

        case GC_STAGE_PRUNE:
            LOG(TRACE, "GC_STAGE_PRUNE");
            stage = gc_fsa_prune();
            atomic_store(&fsa_lock, false);
            return true;

        default:
            abort();
    }

    return true;
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


EXPORT void _gc_write_barrier2(object_t **field, uint32_t mask) {
    while (mask) {
        ptrdiff_t index = __builtin_ctz(mask);
        mask &= mask-1;
        _gc_mark_as_seen2(field[index]);
    }
}


EXPORT void gc_start() {
    assert(stage == GC_STAGE_NOT_STARTED);
    stage = GC_STAGE_IDLE;
}

EXPORT void object_gc_init() {
}




