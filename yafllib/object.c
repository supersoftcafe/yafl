
#include "common.h"
#include "yafl.h"
#include <malloc.h>
#include <setjmp.h>

#define COMPACT_THRESHOLD_PERCENT   33
#define PAGES_SCANNED_PER_ALLOC     12
#define PAGES_PRUNED_PER_ALLOC      12
#define COUNT_TO_FSA                1024

#undef DISABLE_HEAP_COMPACTION



EXPORT bool gc_enabled = false; // Thread controller will prevent GC until all threads are active and registered

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

typedef struct {
    uintptr_t a[GC_SLOT_SIZE / sizeof(uintptr_t)];
} __attribute__((aligned(GC_SLOT_SIZE))) slot_t;

typedef struct page_head {
    bitmap_t     object_heads;  // Allocator marks here, scanner un-marks, to show first slot of objects
    bitmap_t       marks_seen;  // Scanner marks here for every reference seen
    bitmap_t    marks_scanned;  // Scanner marks here to show work done

    struct gc_page      *next;  // Page sits in one of many lists during its lifetime
    size_t         page_count;  // Number of pages, including this one, in the complete allocation
    uint32_t     magic_number;  // Safety check

    bool   should_not_compact;  // If some pinned reference is found, we'll not compact this page.
    bool    mutable_container;  // Contains mutable objects.
    bool previously_compacted;  // Don't compact again.
    bool collection_candidate;

} __attribute__((aligned(GC_SLOT_SIZE))) page_head_t;

enum { PAGE_MAGIC_NUMBER = 0x71ea05c3 };

enum { SLOTS_PER_PAGE = (GC_PAGE_SIZE - sizeof(page_head_t)) / sizeof(slot_t) };

typedef struct gc_page {
    page_head_t head;
    slot_t slots[SLOTS_PER_PAGE];
} __attribute__((aligned(GC_SLOT_SIZE))) gc_page_t;

static_assert(sizeof(gc_page_t) == GC_PAGE_SIZE, "Page size doesn't add up");
static_assert(sizeof(slot_t) == GC_SLOT_SIZE, "Slot size doesn't add up");

enum { MAX_OBJECT_SIZE = sizeof(gc_page_t) - offsetof(gc_page_t, slots[0]) };


static void bitmap_reset_all(bitmap_t* bitmap) {
    memset(bitmap, 0, sizeof(bitmap_t));
}

static void bitmap_and(bitmap_t* target, const bitmap_t* source) {
    for (int index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index)
        target->a[index] &= source->a[index];
}

static void bitmap_andnot(bitmap_t* target, const bitmap_t* source) {
    for (int index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index)
        target->a[index] &= ~source->a[index];
}

static bool bitmap_test_any(bitmap_t* bitmap) {
    for (int index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index)
        if (bitmap->a[index])
            return true;
    return false;
}

static size_t bitmap_count(bitmap_t *bitmap) {
    size_t total = 0;
    for (size_t index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index)
        total += __builtin_popcount(bitmap->a[index]);
    return total;
}

static bool bitmap_test(bitmap_t* bitmap, ptrdiff_t bit) {
    return (bitmap->a[bit / GC_MASK_SIZE] & (((mask_bits_t)1) << (bit % GC_MASK_SIZE))) != 0;
}

static void bitmap_set(bitmap_t* bitmap, ptrdiff_t bit) {
    atomic_fetch_or((_Atomic(mask_bits_t)*)&bitmap->a[bit / GC_MASK_SIZE], ((mask_bits_t)1) << (bit % GC_MASK_SIZE));
}

static void bitmap_unset(bitmap_t* bitmap, ptrdiff_t bit) {
    atomic_fetch_and((_Atomic(mask_bits_t)*)&bitmap->a[bit / GC_MASK_SIZE], ~(((mask_bits_t)1) << (bit % GC_MASK_SIZE)));
}

static void gc_fsa(bool real_work);



enum gc_stage {
    GC_STAGE_IDLE,                    // Nothing happening, waiting for GC to start
    GC_STAGE_SCAN_ROOTS,              // Trying to scan stack. Globals scanned as we exited idle.
    GC_STAGE_SCAN_ROOTS_COMPLETE,     //
    GC_STAGE_MARK_SWEEP,              // Walk the graph, mark things as seen and scan as we go
    GC_STAGE_MARK_SWEEP_COMPLETE,     // Per thread, thinks that scan is complete after stealing etc
    GC_STAGE_PRUNE,    // Releasing unused pages and wiping bits on others ready for next scan
    GC_STAGE_PRUNE_COMPLETE,          // Per thread, thinks that prune is complete after checking other threads too

    // Used to safely move between stages. Consider the MARK_SWEEP_COMPLETE to MARK_SWEEP transition. It is done across
    // all threads at once, but before we've finished one of threads might notice the change, and see that all the others
    // are still in MARK_SWEEP_COMPLETE stage. It might trigger further stage movement. To avoid this we first set all
    // thread stages to STAGE_TEMP, then we move to MARK_SWEEP.
    GC_STAGE_TEMP,

    // During a batch of page scanning or pruning the stage will be set to WORKING so that no two threads
    // accidentaly do a transition at the same time. This is due to contention from the work stealing that
    // is going on, and the need to stop a thread from doing work thinking that the target is at stage
    // MARK_SWEEP (or PRUNING_AND_CLEANING) but it transitions due to a work stealing thread before this
    // thread does some work. It can result in corruption, and nasty bugs.
    GC_STAGE_WORKING,
};

enum thread_state {
    THREAD_STATE_RUNNING,               // Busy running, don't interrupt
    THREAD_STATE_SUSPENDED,             // IO is in progress, so an external thread could scan this thread
    THREAD_STATE_SUSPENDED_SCAN,        // Thread is suspended, an external thread is scanning this one
    THREAD_STATE_EXITED
};



typedef struct bump_pointers {
    char *bump_pointer; // -size to get next object reference
    char *base_pointer; // until <base_pointer, then we need to ask for more
} bump_pointers_t;

thread_local struct gc_thread_info {
    struct gc_thread_info *next;
    thread_roots_declaration_func_t thread_roots_declaration_func;
    void* thread_roots_context;

    _Atomic(enum gc_stage)     gc_stage;
    _Atomic(enum thread_state) thread_state;

    bump_pointers_t region_mutable;
    bump_pointers_t region_immutable;

    _Atomic(gc_page_t*) alloc_head;
    _Atomic(gc_page_t*) scan_head;
    _Atomic(gc_page_t*) scan_result;

    bool scanned_something_of_interest; // Never set by different threads, but might be reset by another thread...
    size_t prune_count_of_used_space;
    size_t prune_count_of_copied_pages;

    object_t **stack_lower_pointer; // Numerically lower pointer to the stack
    object_t **stack_upper_pointer; // Numerically higher pointer to the stack
    struct { jmp_buf jb; } saved_registers[1]; // Expensive way to save the registers for GC

    struct size_by_name {
        const char* name;
        size_t      size;
        size_t     count;
    } size_by_name[10];

    size_t count_to_fsa;

} gc_thread_info;

static _Atomic(struct gc_thread_info*) threads = NULL;
static atomic_bool global_lock = false;


static void fillmem(uint32_t* memory, uint32_t value, size_t count) {
    for (size_t index = 0; index < count; ++index) {
        memory[index] = value;
    }
}

static atomic_size_t gc_page_alloc_counter = 0;
static gc_page_t* gc_page_alloc(size_t page_count) {
    LOG(TRACE, "gc_page_alloc(%ld)", page_count);

    gc_page_t* page = memory_pages_alloc(page_count);
    if (page == NULL)
        abort_on_out_of_memory();

    memset(page, 0, GC_PAGE_SIZE * page_count);
    page->head.page_count = page_count;
    page->head.magic_number = PAGE_MAGIC_NUMBER;

#ifndef NDEBUG
    atomic_fetch_add(&gc_page_alloc_counter, 1);
#endif

    return page;
}

static atomic_size_t gc_page_free_counter = 0;
static void gc_page_free(gc_page_t* page) {
    assert(page->head.magic_number == PAGE_MAGIC_NUMBER);
    page->head.magic_number = 0;
    memory_pages_free(page, page->head.page_count);
#ifndef NDEBUG
    atomic_fetch_add(&gc_page_free_counter, 1);
#endif
}

static void object_get_page_and_slot(object_t* ptr, gc_page_t** page_out, ptrdiff_t* slot_out) {
    *page_out = (gc_page_t*)((intptr_t)ptr & ~(sizeof(gc_page_t)-1));
    *slot_out = (slot_t*)ptr - (*page_out)->slots;
    assert( (*page_out)->head.magic_number == PAGE_MAGIC_NUMBER );
    assert( (*slot_out) >= 0 && (*slot_out) < SLOTS_PER_PAGE );
}


static void default_roots_declaration_func() { }
static roots_declaration_func_t declare_roots_yafl = default_roots_declaration_func;
EXPORT roots_declaration_func_t add_roots_declaration_func(roots_declaration_func_t f) {
    roots_declaration_func_t previous = declare_roots_yafl;
    declare_roots_yafl = f;
    return previous;
}


static bool object_is_on_heap(object_t *ptr) {
    return ptr != NULL
        && ((intptr_t)ptr & 3) == 0             // Avoid data packed into the pointer, like small integers and strings.
        && ((intptr_t)ptr->vtable & 3) != 0;    // Avoid static declared objects, because they don't have a heap header.
}

EXTERN void object_mark_as_seen(object_t *object) {
    gc_page_t* page; ptrdiff_t slot;
    object_get_page_and_slot(object, &page, &slot);
    if (page->head.collection_candidate) {
        vtable_t* vt = VT_TAG_UNSET(object->vtable);
        if (vt->is_mutable)
            LOG(ULTRA, "SEEN(0x%lx) -> %s", (uintptr_t)object, vt->name);

        assert(bitmap_test(&page->head.object_heads, slot));
        bitmap_set(&page->head.marks_seen, slot);
    }
}

static void object_gc_seen_by_field(object_t **field_ptr) {
    object_t *object = *field_ptr;
    if (object_is_on_heap(object)) {
        object_mark_as_seen(object);
        for (vtable_t *vt; UNLIKELY(VT_TAG_GET(vt = object->vtable) == VT_TAG_FORWARD); ) {
            *field_ptr = object = (object_t*)VT_TAG_UNSET(vt);
            object_mark_as_seen(object);
        }
    }
}

static void object_gc_seen_by_value_maybe(object_t *object) {
    if (object_is_on_heap(object) && memory_pages_is_heap(object)) {
        gc_page_t* page; ptrdiff_t slot;
        object_get_page_and_slot(object, &page, &slot);
        if (bitmap_test(&page->head.object_heads, slot)) {
            vtable_t *vt = object_get_vtable(object);
            const char *name = vt->name;

            bitmap_set(&page->head.marks_seen, slot);
            page->head.should_not_compact = 1;
        }
    }
}

static size_t _object_size(object_t* ptr) {
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

static void* _object_alloc(size_t size, bool is_mutable, bool allow_gc) {
    size_t actual_size = (size + sizeof(slot_t) - 1) / sizeof(slot_t) * sizeof(slot_t);

    if (actual_size > MAX_OBJECT_SIZE) {
        // size_t page_count = (sizeof(gc_page_head_t) + actual_size + GC_PAGE_SIZE - 1) / GC_PAGE_SIZE;
        // gc_page_t* page = _gc_page_alloc(page_count);
        // page->head.object_heads.a[0] = 1;
        // return page->slots;
        abort_on_too_large_object();
    }

    struct bump_pointers *bp = is_mutable
        ? &gc_thread_info.region_mutable
        : &gc_thread_info.region_immutable;

    if (UNLIKELY(bp->bump_pointer - bp->base_pointer < actual_size)) {
        if (allow_gc) {
            gc_fsa(true);
        }

        gc_page_t* new_page = gc_page_alloc(1);
        new_page->head.mutable_container = is_mutable;

        bp->base_pointer = (char*)(new_page->slots);
        bp->bump_pointer = (char*)(new_page->slots + SLOTS_PER_PAGE);

        new_page->head.next = gc_thread_info.alloc_head;
        gc_thread_info.alloc_head = new_page;
    }

    object_t *object = (object_t*)(bp->bump_pointer -= actual_size);

    gc_page_t *page ; ptrdiff_t slot ;
    object_get_page_and_slot(object, &page, &slot);
    bitmap_set(&page->head.object_heads, slot);
    // bitmap_set(&page->head.marks_seen, slot);

    return object;
}

EXPORT void* object_create(vtable_t *vtable) {
    assert(vtable->array_el_size == 0);
    object_t *object = _object_alloc(vtable->object_size, vtable->is_mutable, true);
    object->vtable = VT_TAG_SET(vtable, VT_TAG_MANAGED);
    if (vtable->is_mutable)
        LOG(ULTRA, "ALLOC(0x%lx) -> %s", (uintptr_t)object, vtable->name);
    return object;
}

EXPORT void* array_create(vtable_t *vtable, int32_t length) {
    assert(length >= 0);
    assert(vtable->array_el_size != 0);
    object_t *object = _object_alloc(vtable->object_size + vtable->array_el_size*length, vtable->is_mutable, true);
    object->vtable = VT_TAG_SET(vtable, VT_TAG_MANAGED);
    *((int32_t*)(((char*)object)+(vtable->array_len_offset))) = length;
    if (vtable->is_mutable)
        LOG(ULTRA, "ALLOC(0x%lx) -> %s", (uintptr_t)object, vtable->name);
    return object;
}




static void gc_scan_elements(object_t **ptr, uint32_t pointer_locations) {
    for (int index = 0; index < 32; ++index) {
        if (pointer_locations & (1 << index)) {
            object_gc_seen_by_field(&ptr[index]);
        }
    }
}

static void gc_scan_object_meat(object_t *object) {
    vtable_t *vt = object->vtable;
    for (object_t *ptr = object; UNLIKELY(VT_TAG_GET(vt) == VT_TAG_FORWARD); ) {
        ptr = (object_t*)((uintptr_t)vt &~ 3);
        object_mark_as_seen(ptr);
        vt = ptr->vtable;
    }
    vt = (vtable_t*)((uintptr_t)vt &~ 3);

    if (vt->object_pointer_locations) {
        gc_scan_elements((object_t**)object, vt->object_pointer_locations);
    }

    if (vt->array_el_pointer_locations) {
        uint32_t len = *(uint32_t*)&((char*)object)[vt->array_len_offset];
        char*  array = ((char*)object) + vt->object_size;
        for (; len-- > 0; array += vt->array_el_size) {
            gc_scan_elements((object_t**)array, vt->array_el_pointer_locations);
        }
    }
}

HIDDEN void gc_scan_object_shallow(object_t *ptr) {
    if (!object_is_on_heap(ptr)) {
        return;
    }

    gc_page_t* page; ptrdiff_t slot;
    object_get_page_and_slot(ptr, &page, &slot);
    assert(bitmap_test(&page->head.object_heads, slot));

    gc_scan_object_meat(ptr);
    bitmap_set(&page->head.marks_scanned, slot);
}



EXPORT vtable_t *object_get_vtable(object_t *object) {
    vtable_t *vt = object->vtable;
    while (UNLIKELY(VT_TAG_GET(vt) == VT_TAG_FORWARD)) {
        object_t *next_object = (object_t*)VT_TAG_UNSET(vt);
        vt = next_object->vtable;
    }
    return VT_TAG_UNSET(vt);
}

EXPORT fun_t vtable_lookup(object_t *object, intptr_t id) {
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

EXPORT void object_set_reference(object_t *object, size_t field_offset, object_t *value) {
    object_t **field = (object_t**)&((char*)object)[field_offset];
    object_t *old_value = *field;
    if (object_is_on_heap(old_value))
        object_mark_as_seen(old_value);
    // if (object_is_on_heap(value))
    //     mark_as_seen(value);
    *field = value;
}






static bool is_object_head(slot_t* ptr) {
    gc_page_t* page = (gc_page_t*)((uintptr_t)ptr &~ (GC_PAGE_SIZE-1));
    ptrdiff_t slot = ptr - page->slots;
    return slot >= 0 && slot < SLOTS_PER_PAGE && bitmap_test(&page->head.object_heads, slot);
}

static bool gc_pointer_is_into_heap(slot_t* ptr) {
    return ptr != NULL
        && ((intptr_t)ptr & (GC_SLOT_SIZE-1)) == 0
        && memory_pages_is_heap(ptr)
        && is_object_head(ptr);
}

static void _gc_scan_range(object_t** range_ptr, object_t** range_end) {
    for (; range_ptr != range_end; range_ptr++) {
        object_t* ptr = *range_ptr;
        if (gc_pointer_is_into_heap((slot_t*)ptr)) {
            object_gc_seen_by_value_maybe(ptr);
        }
    }
}

static void gc_zero_page_flags(gc_page_t* page) {
    page->head.should_not_compact = false;
    bitmap_reset_all(&page->head.marks_seen);
    bitmap_reset_all(&page->head.marks_scanned);
}

static void donothing() {

}

static bool change_thread_state(struct gc_thread_info *thread_info, enum thread_state expected, enum thread_state desired) {
  return atomic_compare_exchange_strong(&thread_info->thread_state, &expected, desired);
}

static NOINLINE void update_stack_address_and_registers() {
    object_t* some_random_var = NULL;
#ifdef STACK_GROWS_DOWN
    gc_thread_info.stack_lower_pointer = &some_random_var;
#else
    thread->stack_upper_pointer = &some_random_var;
#endif
    setjmp(gc_thread_info.saved_registers[0].jb);
}

// Start of potentially thread pausing IO
EXPORT void object_gc_io_begin() {
    object_gc_safe_point();

    assert(gc_thread_info.thread_state == THREAD_STATE_RUNNING);

    update_stack_address_and_registers();
    atomic_store(&gc_thread_info.thread_state, THREAD_STATE_SUSPENDED);
}

// End of potentially thread pausing IO
EXPORT void object_gc_io_end() {
    do {
        assert(gc_thread_info.thread_state == THREAD_STATE_SUSPENDED || gc_thread_info.thread_state == THREAD_STATE_SUSPENDED_SCAN);
    } while (!change_thread_state(&gc_thread_info, THREAD_STATE_SUSPENDED, THREAD_STATE_RUNNING));
}

// Any thread that can do allocation must call this early on
EXPORT void object_gc_declare_thread(thread_roots_declaration_func_t thread_roots_declaration_func, void*thread_roots_context) {
    object_t* some_random_var = NULL;
#ifdef STACK_GROWS_DOWN
    gc_thread_info.stack_upper_pointer = &some_random_var;
#else
    _thread_info.stack_lower_pointer = &some_random_var;
#endif

    gc_thread_info.thread_roots_declaration_func = thread_roots_declaration_func;
    gc_thread_info.thread_roots_context = thread_roots_context;

    gc_thread_info.next = threads;
    gc_thread_info.thread_state = THREAD_STATE_RUNNING;
    while (!atomic_compare_exchange_weak(&threads, &gc_thread_info.next, &gc_thread_info));

}

static NOINLINE bool gc_scan_page(gc_page_t* page) {
    bool didSome = false;
    for (ptrdiff_t index = 0; index < sizeof(bitmap_t) / sizeof(mask_bits_t); ++index) {
        assert( (page->head.marks_scanned.a[index] &~ page->head.marks_seen.a[index]) == 0 );
        assert( (page->head.marks_seen.a[index] &~ page->head.object_heads.a[index]) == 0 );

        mask_bits_t candidate_bits = page->head.marks_seen.a[index] &~ page->head.marks_scanned.a[index];
        if (candidate_bits != 0) {
            int low_zeros_count = __builtin_ctzll(candidate_bits);
            ptrdiff_t slot = index * GC_MASK_SIZE + low_zeros_count;

            assert(bitmap_test(&page->head.object_heads, slot));

            gc_thread_info.scanned_something_of_interest = true;
            gc_scan_object_shallow((object_t*)&page->slots[slot]);

            didSome = true;
            index = -1; // Loop increment will bring it to 0
        }
    }
    return didSome;
}

static int _compare_entry(const struct size_by_name* a, const struct size_by_name* b) {
    if (a->name == b->name) {
        return 0;
    } else if (b->name == NULL) {
        return 1;
    } else if (a->name == NULL) {
        return -1;
    } else {
        return strcmp(a->name, b->name);
    }
}

static void add_size(const char* name, size_t size) {
    if (name == NULL) {
        name = "null";
    }
    for (int index = 0; index < 10; ++index) {
        struct size_by_name *e = &gc_thread_info.size_by_name[index];
        if (e->name == name) {
            e->size += size;
            e->count ++;
            return;
        } else if (e->name == NULL) {
            e->name = name;
            e->size = size;
            e->count = 1;
            return;
        }
    }
}

static NOINLINE void gc_clear_unused_space(gc_page_t *page) {
    ptrdiff_t counter = 0;
    size_t used_bytes = 0;
    for (ptrdiff_t slot = 0; slot < SLOTS_PER_PAGE; ++slot) {
        if (bitmap_test(&page->head.object_heads, slot)) {
            if (bitmap_test(&page->head.marks_seen, slot)) {

                object_t* obj = (object_t*)&page->slots[slot];
                size_t size = _object_size(obj);
                used_bytes += size;
                add_size(object_get_vtable(obj)->name, size);
                counter = size / sizeof(slot_t);
                assert(counter > 0);

            } else {

                object_t *obj = (object_t*)&page->slots[slot];
                vtable_t *vt = VT_TAG_UNSET(obj->vtable);

                if (vt->is_mutable)
                    LOG(ULTRA, "FREE(0x%lx) -> %s", (uintptr_t)obj, vt->name);

                bitmap_unset(&page->head.object_heads, slot);

            }
        }
        if (--counter < 0) {
            // Fill unused space to cause crashes if GC gets it wrong
            fillmem((uint32_t*)&page->slots[slot], 0xdeadbeef, sizeof(slot_t) / sizeof(uint32_t));
        }
    }
    gc_thread_info.prune_count_of_used_space += used_bytes;
}


static NOINLINE void gc_compact_page(gc_page_t *page) {
    size_t slots_threshold = SLOTS_PER_PAGE * COMPACT_THRESHOLD_PERCENT / 100;

    if (page->head.previously_compacted) {
        gc_thread_info.prune_count_of_copied_pages += 1;
        return; // Compacted on previous prune. We count these to track overhead stats.
    }

    if (page->head.mutable_container || page->head.should_not_compact || page->head.page_count > 1) {
        return; // Not for compaction
    }

    if (bitmap_count(&page->head.object_heads) > slots_threshold) {
        return; // Too big for compaction, don't even need to add up object sizes.
    }

    size_t object_count = 0;
    struct obj_and_sze { object_t *o; size_t s; };
    struct obj_and_sze *objects = alloca(sizeof(struct obj_and_sze) * slots_threshold);

    size_t total = 0;
    for (ptrdiff_t slot = SLOTS_PER_PAGE; --slot >= 0; ) {
        if (bitmap_test(&page->head.object_heads, slot)) {
            object_t *object = (object_t*)&page->slots[slot];
            size_t size = _object_size(object);
            objects[object_count++] = (struct obj_and_sze){ .o = object, .s = size };

            total += size;
            if (total > SLOTS_PER_PAGE*sizeof(slot_t)/3) {
                return; // Too big for compaction
            }
        }
    }

    if (page->head.previously_compacted) {
        return; // Another thread got there first
    }

    while (object_count-- > 0) {
        object_t *object = objects[object_count].o;
        size_t      size = objects[object_count].s;

        object_t *target = _object_alloc(size, false, false);// Allocate new object
        memcpy(target, object, size);                        // Copy contents across
        object->vtable = VT_TAG_SET(target, VT_TAG_FORWARD); // Set forwarding pointer
    }

    page->head.previously_compacted = true;
}


static bool gc_acquire_global_lock() {
    bool expected = false;
    // We are ok with a few false negatives, so cas_weak might be
    // better here, for a little extra performance on non x86 systems
    return atomic_compare_exchange_strong(&global_lock, &expected, true);
}

static void gc_release_global_lock() {
#ifndef NDEBUG
    bool expected = true;
    bool success = atomic_compare_exchange_strong(&global_lock, &expected, false);
    assert(success);
#else
    atomic_store(&global_lock, false);
#endif
}






static void snapshot_scan_pages(struct gc_thread_info *thread_info) {
    assert(thread_info->thread_state == THREAD_STATE_RUNNING);
    assert(thread_info->gc_stage == GC_STAGE_SCAN_ROOTS);

    // Capture pages ready for mark sweep
    gc_page_t *scan_head = thread_info->scan_result; // Final result of last scan
    gc_page_t *new_pages = thread_info->alloc_head;  // Allocations since last scan

    while (new_pages != NULL) {
        gc_page_t *page = new_pages; // Unlink from allocations list
        new_pages = page->head.next;

        page->head.collection_candidate = true;

        page->head.next = scan_head; // Link into scan list
        scan_head = page;
    }

    thread_info->alloc_head = NULL;
    thread_info->scan_head = scan_head;
    thread_info->scan_result = NULL;
    thread_info->scanned_something_of_interest = false;
    thread_info->prune_count_of_used_space = 0;

    thread_info->region_immutable.base_pointer = thread_info->region_mutable.base_pointer = NULL;
    thread_info->region_immutable.bump_pointer = thread_info->region_mutable.bump_pointer = NULL;
}

static void scan_thread_roots(struct gc_thread_info *thread_info) {
    // Scan stack and registers
    _gc_scan_range(thread_info->stack_lower_pointer, thread_info->stack_upper_pointer);
    _gc_scan_range((object_t**)&thread_info->saved_registers[0], (object_t**)&thread_info->saved_registers[1]);

    // Thread library has some stuff
    thread_info->thread_roots_declaration_func(thread_info->thread_roots_context, object_gc_seen_by_field);
}

static bool take_page_and_scan(struct gc_thread_info *thread_info) {
    // Take a page from the given thread. We might be stealing, so this must be done safely.
    gc_page_t *page = thread_info->scan_head;
    while (page && !atomic_compare_exchange_strong(&thread_info->scan_head, &page, page->head.next));
    if (page == NULL) {
        return false;
    }

    // Scan the page
    gc_scan_page(page);

    // Put it back in our thread local results area. No other thread touches this whilst scanning.
    page->head.next = gc_thread_info.scan_result;
    gc_thread_info.scan_result = page;
    return true;
}

static bool take_page_and_prune(struct gc_thread_info *thread_info) {
    // Take a page from the given thread. We might be stealing, so this must be done safely.
    gc_page_t *page = thread_info->scan_head;
    while (page && !atomic_compare_exchange_strong(&thread_info->scan_head, &page, page->head.next));
    if (page == NULL) {
        return false; // False means that there weren't any pages to process
    }

#ifdef NDEBUG
    // Mask out the things that no longer exist
    bitmap_and(&page->head.object_heads, &page->head.marks_seen);
#else
    // Whether we release or not, in debug mode we want to write rubbish to unused space
    gc_clear_unused_space(page); // TODO: Log things that are removed, and then clear the object_heads bit
#endif

    // If nothing is retained on this page, release it back to the system.
    if (!bitmap_test_any(&page->head.object_heads)) {
        gc_page_free(page);
        return true; // True means that we found and processed a page
    }

    bitmap_reset_all(&page->head.marks_seen);
    bitmap_reset_all(&page->head.marks_scanned);

#ifndef DISABLE_HEAP_COMPACTION
    // Is compaction an option? Should we do it?
    gc_compact_page(page);
#endif

    // Page survived pruning. Put it back in our thread local results area.
    // Even a compacted page survives. It usually gets reclaimed on the next pass.
    page->head.next = gc_thread_info.scan_result;
    gc_thread_info.scan_result = page;

    return true; // True means that we found and processed a page
}

static bool fsa_consensus_change_stage(enum gc_stage from_stage, enum gc_stage (*action)()) {
    // Use the global lock, to ensure that only one thread succeeds at this
    if (!gc_acquire_global_lock()) {
        return false;
    }

    // Are all threads in the 'from_stage'. The stage must be stable such that threads only enter
    // this stage and then require an external actor to move the out, like this function.
    for (struct gc_thread_info *thread_info = threads; thread_info != NULL; thread_info = thread_info->next) {
        if (thread_info->gc_stage != from_stage) {
            gc_release_global_lock();
            return false;
        }
    }

    // Perform some action that needs the global lock, and determines next stage
    enum gc_stage to_stage = action();

    for (struct gc_thread_info *thread_info = threads; thread_info != NULL; thread_info = thread_info->next) {
        thread_info->gc_stage = GC_STAGE_TEMP;
    }

    for (struct gc_thread_info *thread_info = threads; thread_info != NULL; thread_info = thread_info->next) {
        thread_info->gc_stage = to_stage;
    }

    gc_release_global_lock();
    return true;
}







static enum gc_stage gc_fsa_idle$action() {
    return GC_STAGE_SCAN_ROOTS;
}
static void gc_fsa_idle() {
    if (gc_enabled) {
        // If all threads are idle, scan global roots, and then ask threads to scan their roots.
        fsa_consensus_change_stage(GC_STAGE_IDLE, gc_fsa_idle$action);
    }
}

static void gc_fsa_scan_thread_local_roots(struct gc_thread_info *thread_info) {
    // Capture pages ready for mark sweep
    snapshot_scan_pages(thread_info);

    // Scan stack and thread local roots
    scan_thread_roots(thread_info);

    // Reset the statistics gathering array
    memset(thread_info->size_by_name, 0, sizeof(thread_info->size_by_name));

    thread_info->gc_stage = GC_STAGE_SCAN_ROOTS_COMPLETE;
}

static enum gc_stage gc_fsa_scan_roots_complete$action() {
    declare_roots_thread(object_gc_seen_by_field);
    declare_roots_yafl(object_gc_seen_by_field);
    return GC_STAGE_MARK_SWEEP;
}
static void gc_fsa_scan_roots_complete() {
    // If all threads are scanned, move on to mark sweep
    if (!fsa_consensus_change_stage(GC_STAGE_SCAN_ROOTS_COMPLETE, gc_fsa_scan_roots_complete$action)) {

        // Try to scan other threads
        for (struct gc_thread_info *thread_info = threads; thread_info != NULL; thread_info = thread_info->next) {
            if (thread_info->gc_stage == GC_STAGE_SCAN_ROOTS && change_thread_state(thread_info, THREAD_STATE_SUSPENDED, THREAD_STATE_SUSPENDED_SCAN)) {

                // We've now locked access to the thread structure, but stage could have changed, so check again
                if (thread_info->gc_stage == GC_STAGE_SCAN_ROOTS) {

                    // Nobody else is able to do this now that we've effectively locked the thread
                    // It is doing IO so it's safe, and it can't exit the IO block now that we have the lock
                    gc_fsa_scan_thread_local_roots(thread_info);
                }
            }
        }
    }
}

static void gc_fsa_mark_sweep() {
    // Scan pages, putting results into our threads result
    enum gc_stage expected = GC_STAGE_MARK_SWEEP;
    if (atomic_compare_exchange_strong(&gc_thread_info.gc_stage, &expected, GC_STAGE_WORKING)) {
        for (int count = PAGES_SCANNED_PER_ALLOC; --count >= 0; ) {
            if (!take_page_and_scan(&gc_thread_info)) {
                bool scanned_something = false;

                // There was nothing to scan, try stealing more work from other threads
                for (struct gc_thread_info *thread_info = threads; thread_info != NULL; thread_info = thread_info->next) {
                    scanned_something = take_page_and_scan(thread_info);
                }

                if (!scanned_something) {
                    // This thread has run out of work
                    gc_thread_info.gc_stage = GC_STAGE_MARK_SWEEP_COMPLETE;
                    return;
                }
            }
        }
        gc_thread_info.gc_stage = GC_STAGE_MARK_SWEEP;
    }
}

static enum gc_stage gc_fsa_mark_sweep_complete$action() {
    enum gc_stage to_stage = GC_STAGE_PRUNE;
    for (struct gc_thread_info *thread_info = threads; thread_info != NULL; thread_info = thread_info->next) {

        // Reset ready for next scan, or for pruning. It's all the same.
        thread_info->scan_head = thread_info->scan_result;
        thread_info->scan_result = NULL;

        if (thread_info->scanned_something_of_interest) {
            thread_info->scanned_something_of_interest = false;
            to_stage = GC_STAGE_MARK_SWEEP;
        }
    }
    return to_stage;
}
static void gc_fsa_mark_sweep_complete() {
    // Attempt the transition away from MARK_SWEEP_COMPLETE
    if (!fsa_consensus_change_stage(GC_STAGE_MARK_SWEEP_COMPLETE, gc_fsa_mark_sweep_complete$action)) {

        // If some thread managed to work steel another thread to empty, it could be stuck on MARK_SWEEP
        for (struct gc_thread_info *thread_info = threads; thread_info != NULL; thread_info = thread_info->next) {
            if (thread_info->scan_head == NULL) {
                enum gc_stage expected = GC_STAGE_MARK_SWEEP;
                atomic_compare_exchange_strong(&thread_info->gc_stage, &expected, GC_STAGE_MARK_SWEEP_COMPLETE);
            }
        }
    }
}

static void gc_fsa_prune() {
    // Prune pages, putting results into our threads result
    enum gc_stage expected = GC_STAGE_PRUNE;
    if (atomic_compare_exchange_strong(&gc_thread_info.gc_stage, &expected, GC_STAGE_WORKING)) {
        for (int count = PAGES_PRUNED_PER_ALLOC; --count >= 0; ) {
            if (!take_page_and_prune(&gc_thread_info)) {
                bool pruned_something = false;

                // There was nothing to prune, try stealing more work from other threads
                for (struct gc_thread_info *thread_info = threads; thread_info != NULL; thread_info = thread_info->next) {
                    pruned_something = take_page_and_prune(thread_info);
                }

                if (!pruned_something) {
                    // This thread has run out of work
                    gc_thread_info.gc_stage = GC_STAGE_PRUNE_COMPLETE;
                    return;
                }
            }
        }
        gc_thread_info.gc_stage = GC_STAGE_PRUNE;
    }
}

static enum gc_stage gc_fsa_prune_complete$action() {
    return GC_STAGE_IDLE;
}
static void gc_fsa_prune_complete() {
    // Attempt the transition away from PRUNE_COMPLETE
    if (!fsa_consensus_change_stage(GC_STAGE_PRUNE_COMPLETE, gc_fsa_prune_complete$action)) {

        // If some thread managed to work steel another thread to empty, it could be stuck on PRUNE
        for (struct gc_thread_info *thread_info = threads; thread_info != NULL; thread_info = thread_info->next) {
            if (thread_info->scan_head == NULL) {
                enum gc_stage expected = GC_STAGE_PRUNE;
                atomic_compare_exchange_strong(&thread_info->gc_stage, &expected, GC_STAGE_PRUNE_COMPLETE);
            }
        }
    }
}

EXPORT void object_gc_safe_point() {
    assert(gc_thread_info.thread_state == THREAD_STATE_RUNNING);
    if (--gc_thread_info.count_to_fsa == 0) {
        gc_thread_info.count_to_fsa = COUNT_TO_FSA;

        // Certain transitions can only occur from within the owning thread, or whilst blocked on IO
        // Safe points ensure that these occur even when no allocations are occuring on the thread

        gc_fsa(false);
    }
}

// Arbitary safe point for GC magic to happen
static void gc_fsa(bool real_work) {
    assert(gc_thread_info.thread_state == THREAD_STATE_RUNNING);

    static size_t iteration_count = 0;

    switch (gc_thread_info.gc_stage) {
        case GC_STAGE_IDLE:
            LOG(TRACE, "IDLE {%ld,%ld}", gc_page_alloc_counter, gc_page_free_counter);
            iteration_count = 0;
            gc_fsa_idle();
            break;

        case GC_STAGE_SCAN_ROOTS:
            LOG(TRACE, "SCAN_ROOTS {%ld,%ld}", gc_page_alloc_counter, gc_page_free_counter);
            update_stack_address_and_registers();
            gc_fsa_scan_thread_local_roots(&gc_thread_info);
            break;

        case GC_STAGE_SCAN_ROOTS_COMPLETE:
            LOG(TRACE, "SCAN_ROOTS_COMPLETE {%ld,%ld}", gc_page_alloc_counter, gc_page_free_counter);
            gc_fsa_scan_roots_complete();
            break;

        case GC_STAGE_MARK_SWEEP:
            if (real_work) {
                LOG(TRACE, "MARK_SWEEP {%ld,%ld} iter=%ld", gc_page_alloc_counter, gc_page_free_counter, iteration_count);
                gc_fsa_mark_sweep();
            }
            break;

        case GC_STAGE_MARK_SWEEP_COMPLETE:
            LOG(TRACE, "MARK_SWEEP_COMPLETE {%ld,%ld} iter=%ld", gc_page_alloc_counter, gc_page_free_counter, iteration_count);
            iteration_count ++;
            gc_fsa_mark_sweep_complete();
            break;

        case GC_STAGE_PRUNE:
            if (real_work) {
                LOG(TRACE, "PRUNE {%ld,%ld}", gc_page_alloc_counter, gc_page_free_counter);
                gc_fsa_prune();
            }
            break;

        case GC_STAGE_PRUNE_COMPLETE:
            LOG(TRACE, "PRUNE_COMPLETE {%ld,%ld}", gc_page_alloc_counter, gc_page_free_counter);
            gc_fsa_prune_complete();
            break;

        case GC_STAGE_TEMP:
        case GC_STAGE_WORKING:
            // Do nothing. These are marker stages used during other transitions.
            break;
    }
}







EXPORT void object_gc_init() {
}




