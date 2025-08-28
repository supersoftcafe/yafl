
#include "common.h"
#include "yafl.h"
#include <malloc.h>


EXPORT void abort_on_vtable_lookup() {
    log_error_and_exit("Aborting due to vtable lookup issue", stderr);
}

EXPORT void abort_on_out_of_memory() {
    log_error_and_exit("Aborting due to memory allocation failure", stderr);
}

EXPORT void abort_on_too_large_object() {
    log_error_and_exit("Aborting due to unsupported object size failure", stderr);
}

EXPORT void abort_on_heap_allocation_on_non_worker_thread() {
    log_error_and_exit("Aborting due to attempted allocation on uninitialised thread", stderr);
}




typedef uintptr_t gc_mask_bits_t;
enum { GC_MASK_SIZE = sizeof(gc_mask_bits_t) * 8 };
enum { GC_PAGE_SIZE = 16384 };
enum { GC_SLOT_SIZE = 32 };

typedef struct gc_bitmap {
    _Atomic(gc_mask_bits_t) a[GC_PAGE_SIZE / GC_SLOT_SIZE / 8 / sizeof(gc_mask_bits_t)];
} __attribute__((aligned(GC_PAGE_SIZE / GC_SLOT_SIZE / 8))) gc_bitmap_t;

typedef struct gc_slot {
    uintptr_t a[GC_SLOT_SIZE / sizeof(uintptr_t)];
} __attribute__((aligned(GC_SLOT_SIZE))) gc_slot_t;

typedef struct gc_page_head {
    struct gc_page*      next;
    size_t         page_count;
    bool    recent_allocation; // Allocated since last GC cycle began
    bool          in_use_lock; // Not allowed to free this block because it is still being used for allocations
    gc_bitmap_t  object_heads; // Bits to mark the starting index of each object
    gc_bitmap_t    marks_seen;
    gc_bitmap_t marks_scanned;
} __attribute__((aligned(GC_SLOT_SIZE))) gc_page_head_t;

enum { GC_SLOTS_PER_PAGE = (GC_PAGE_SIZE - sizeof(gc_page_head_t)) / sizeof(gc_slot_t) };

typedef struct gc_page {
    gc_page_head_t head;
    gc_slot_t slots[GC_SLOTS_PER_PAGE];
} __attribute__((aligned(GC_SLOT_SIZE))) gc_page_t;

static_assert(sizeof(gc_page_t) == GC_PAGE_SIZE, "Page size doesn't add up");
static_assert(sizeof(gc_slot_t) == GC_SLOT_SIZE, "Slot size doesn't add up");

enum { MAX_OBJECT_SIZE = sizeof(gc_page_t) - offsetof(gc_page_t, slots[0]) };


HIDDEN void _bitmap_reset_all(gc_bitmap_t* bitmap) {
    memset(bitmap, 0, sizeof(gc_bitmap_t));
}

HIDDEN bool _bitmap_test_all(gc_bitmap_t* bitmap) {
    for (int index = 0; index < sizeof(gc_bitmap_t)/sizeof(uintptr_t); ++index)
        if (bitmap->a[index])
            return true;
    return false;
}

HIDDEN bool _bitmap_test(gc_bitmap_t* bitmap, ptrdiff_t bit) {
    return (bitmap->a[bit / GC_MASK_SIZE] & (((gc_mask_bits_t)1) << (bit % GC_MASK_SIZE))) != 0;
}

HIDDEN void _bitmap_set(gc_bitmap_t* bitmap, ptrdiff_t bit) {
    atomic_fetch_or(&bitmap->a[bit / GC_MASK_SIZE], ((gc_mask_bits_t)1) << (bit % GC_MASK_SIZE));
}

HIDDEN void _gc_fsa();



typedef enum gc_stage {
    _FSA_LOCKED,

    _FSA_IDLE,          // Wait for next GC         | _gc_stage_count=pages to allocate before next GC
    _FSA_ZERO_FLAGS,    // Write zero to all flags  |
    _FSA_MARK_ROOTS,    // Follow global+thread variables to mark root objects as seen
    _FSA_SCAN_HEAP,     // Scan seen objects on the heap until there are none left to scan
    _FSA_PRUNE_HEAP,    // Remove unused pages from the heap

} gc_stage_t;


/* _gc_stage_count means different things at each stage.
 * At idle, this is the number of pages to have allocated before we start the next gc cycle.
 * At
 */
HIDDEN _Atomic(size_t)  _gc_stage_count = 16; // First GC will occur after 16 page allocations
HIDDEN _Atomic(gc_stage_t)    _gc_stage = _FSA_IDLE;

HIDDEN _Atomic(gc_page_t*)   _all_pages; // All pages that exist, including recent allocations
HIDDEN _Atomic(size_t)   _gc_page_count; // Total page count
HIDDEN _Atomic(bool)    _gc_in_progress;

thread_local struct {
    char*      bump_pointer; // -size to get next object reference
    char*      base_pointer; // until <base_pointer, then we need to ask for more
    gc_page_t* current_page;
    bool        initialised;
} allocator_struct;









HIDDEN gc_page_t* _gc_page_alloc(size_t page_count) {
    gc_page_t* page = aligned_alloc(GC_PAGE_SIZE, GC_PAGE_SIZE * page_count);
    if (page == NULL)
        abort_on_out_of_memory();

    memset(page, 0, GC_PAGE_SIZE * page_count);
    page->head.page_count = page_count;
    page->head.recent_allocation = true;

    page->head.next = _all_pages;
    while (!atomic_compare_exchange_weak(&_all_pages, &page->head.next, page));
    atomic_fetch_add(&_gc_page_count, page_count);

    _gc_fsa();

    return page;
}

HIDDEN void _gc_page_free(gc_page_t** page_ptr) {
    gc_page_t* page = *page_ptr;
    atomic_fetch_sub(&_gc_page_count, page->head.page_count);
    *page_ptr = page->head.next;
    free(page);
}

EXTERN void _object_get_page_and_slot(object_t* ptr, gc_page_t** page_out, ptrdiff_t* slot_out) {
    *page_out = (gc_page_t*)((intptr_t)ptr & ~(sizeof(gc_page_t)-1));
    *slot_out = (gc_slot_t*)ptr - (*page_out)->slots;
}


static void default_roots_declaration_func() { }
HIDDEN roots_declaration_func_t _declare_roots_yafl = default_roots_declaration_func;
EXTERN roots_declaration_func_t add_roots_declaration_func(roots_declaration_func_t f) {
    roots_declaration_func_t previous = _declare_roots_yafl;
    _declare_roots_yafl = f;
    return previous;
}

HIDDEN void _object_declare_root(object_t** object_ptr) {
    object_mark_as_seen(*object_ptr);
}

HIDDEN void _object_declare_roots() {
    declare_roots_thread(_object_declare_root);
    _declare_roots_yafl(_object_declare_root);
}




HIDDEN void* _object_alloc(size_t size) {
    size_t actual_size = (size + sizeof(gc_slot_t) - 1) / sizeof(gc_slot_t) * sizeof(gc_slot_t);

    if (actual_size > MAX_OBJECT_SIZE) {
        // size_t page_count = (sizeof(gc_page_head_t) + actual_size + GC_PAGE_SIZE - 1) / GC_PAGE_SIZE;
        // gc_page_t* page = _gc_page_alloc(page_count);
        // page->head.object_heads.a[0] = 1;
        // return page->slots;
        abort_on_too_large_object();
    }

    if (allocator_struct.bump_pointer - allocator_struct.base_pointer < actual_size) {
        if (allocator_struct.current_page) {
            allocator_struct.current_page->head.in_use_lock = false;
            allocator_struct.current_page->head.recent_allocation = true;
        }

        gc_page_t* page = _gc_page_alloc(1);
        page->head.in_use_lock = true;
        allocator_struct.current_page = page;
        allocator_struct.base_pointer = (char*)(page->slots);
        allocator_struct.bump_pointer = (char*)(page + 1);
    }

    gc_page_t* current_page = allocator_struct.current_page;
    gc_slot_t* ptr = (gc_slot_t*)(allocator_struct.bump_pointer -= actual_size);
    ptrdiff_t slot = ptr - current_page->slots;
    _bitmap_set(&current_page->head.object_heads, slot);

    return ptr;
}

INLINE bool _object_is_on_heap(object_t* ptr) {
    return ((intptr_t)ptr & 3) == 0             // Avoid data packed into the pointer, like small integers and strings.
        && ((intptr_t)ptr->vtable & 3) != 0;    // Avoid static declared objects, because they don't have a heap header.
}

EXPORT void object_mark_as_seen(object_t* ptr) {
    if (ptr != NULL && _object_is_on_heap(ptr)) {
        gc_page_t* page; ptrdiff_t slot;
        _object_get_page_and_slot(ptr, &page, &slot);
        assert(_bitmap_test(&page->head.object_heads, slot));
        _bitmap_set(&page->head.marks_seen, slot);
    }
}



EXTERN void object_allocator_init() {
    allocator_struct.initialised = true;
}

HIDDEN void _gc_scan_elements(object_t** ptr, uint32_t pointer_locations) {
    for (int index = 0; index < 32; ++index) {
        if (pointer_locations & (1 << index)) {
            object_mark_as_seen(ptr[index]);
        }
    }
}

HIDDEN void _gc_scan_object(object_t* ptr) {
    vtable_t* vt = ptr->vtable;

    if (vt->object_pointer_locations) {
        _gc_scan_elements((object_t**)ptr, vt->object_pointer_locations);
    }

    if (vt->array_el_pointer_locations) {
        uint32_t len = *(uint32_t*)&((char*)ptr)[vt->array_len_offset];
        char*  array = ((char*)ptr) + vt->object_size;
        for (; len-- > 0; array += vt->array_el_size) {
            _gc_scan_elements((object_t**)array, vt->array_el_pointer_locations);
        }
    }

    gc_page_t* page; ptrdiff_t slot;
    _object_get_page_and_slot(ptr, &page, &slot);
    _bitmap_set(&page->head.marks_scanned, slot);
}

EXPORT object_t* object_mutation(object_t* ptr) {
    if (_gc_in_progress && _object_is_on_heap(ptr)) {
        gc_page_t* page; ptrdiff_t slot;
        _object_get_page_and_slot(ptr, &page, &slot);
        if (!_bitmap_test(&page->head.marks_scanned, slot)) {
            object_mark_as_seen(ptr);
            _gc_scan_object(ptr);
        }
    }
    return ptr;
}

EXPORT void* object_create(vtable_t* vtable) {
    assert(vtable->array_el_size == 0);
    void* object = _object_alloc(vtable->object_size);
    *(char**)&((object_t*)object)->vtable = ((char*)vtable)+1;
    return object;
}

EXPORT void* array_create(vtable_t* vtable, int32_t length) {
    assert(length >= 0);
    assert(vtable->array_el_size != 0);
    void* object = _object_alloc(vtable->object_size + vtable->array_el_size*length);
    *((int32_t*)(((char*)object)+(vtable->array_len_offset))) = length;
    *(char**)&((object_t*)object)->vtable = ((char*)vtable)+1;
    return object;
}

EXPORT fun_t vtable_lookup(void* object, intptr_t id) {
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












HIDDEN size_t _gc_scan_page(gc_page_t* page) {
    size_t scanned_object_count = 0;
    for (ptrdiff_t index = 0; index < sizeof(gc_bitmap_t) / sizeof(gc_mask_bits_t); ++index) {
        gc_mask_bits_t masked = page->head.marks_seen.a[index] ^ page->head.marks_scanned.a[index];
        if (masked) {
            int counted = __builtin_ctzll(masked);
            int mask_size = GC_MASK_SIZE;
            ptrdiff_t slot = index * mask_size + counted;
            _gc_scan_object((object_t*)&page->slots[slot]);
            scanned_object_count += 1;
        }
    }
    return scanned_object_count;
}


static size_t _gc_scan_heap_object_count = 0;
static gc_page_t* _gc_scan_heap_progress = NULL;
HIDDEN bool _gc_scan_heap() {
    int max_iter_count = 10;

    if (_gc_scan_heap_progress == NULL) {
        _gc_scan_heap_object_count = 0;
        _gc_scan_heap_progress = _all_pages;
    }

    for (; _gc_scan_heap_progress != NULL; _gc_scan_heap_progress = _gc_scan_heap_progress->head.next) {
        if (!_gc_scan_heap_progress->head.recent_allocation) {
            _gc_scan_heap_object_count += _gc_scan_page(_gc_scan_heap_progress);
            if (--max_iter_count <= 0) {
                return false; // Early exit, call again
            }
        }
    }

    // We get here because _gc_scan_heap_progress is NULL, which is the start condition for the next cycle.
    return _gc_scan_heap_object_count == 0; // Only true if all scanning is complete
}

HIDDEN bool _gc_page_is_busy(gc_page_t* page) {
    return page->head.recent_allocation || page->head.in_use_lock || _bitmap_test_all(&page->head.marks_seen);
}

static gc_page_t* _gc_prune_heap_progress = NULL;
HIDDEN bool _gc_prune_heap() {
    int max_iter_count = 100;

    if (_gc_prune_heap_progress == NULL) {
        _gc_prune_heap_progress = _all_pages;
    }

    // Never prune the first page, because multiple threads are updating '_all_pages' so
    // we can't safely update it to point to the following page. That would be an A-B-A
    // issue. However, page->head.next is never updated by multiple threads, so removing
    // any of the following pages from a locked context is safe.

    while (_gc_prune_heap_progress->head.next != NULL) {
        if (_gc_page_is_busy(_gc_prune_heap_progress->head.next)) {
            // Move forward by one
            _gc_prune_heap_progress = _gc_prune_heap_progress->head.next;
            if (!_gc_prune_heap_progress->head.recent_allocation) {
                _gc_prune_heap_progress->head.object_heads = _gc_prune_heap_progress->head.marks_seen;
            }
        } else {
            // Release the page and update the pointer referencing it
            _gc_page_free(&_gc_prune_heap_progress->head.next);

            if (--max_iter_count <= 0) {
                return false;
            }
        }
    }

    _gc_prune_heap_progress = NULL;
    return true;
}

HIDDEN void _gc_zero_all_flags() {
    for (gc_page_t* page = _all_pages; page != NULL; page = page->head.next) {
        _bitmap_reset_all(&page->head.marks_seen);
        _bitmap_reset_all(&page->head.marks_scanned);
        if (!page->head.in_use_lock) {
            page->head.recent_allocation = false;
        }
    }
}

#define _FSA_LOCKED(original_state)\
    case original_state:{\
        gc_stage_t _fsa_state_expected = original_state;\
        if (atomic_compare_exchange_strong(&_gc_stage, &_fsa_state_expected, _FSA_LOCKED)) {\

#define _FSA_LOCKED_END()\
        }\
    } break;

HIDDEN void _gc_fsa() {
    switch (_gc_stage) {
        case _FSA_LOCKED: // Another thread holds a lock
            break;

        _FSA_LOCKED(_FSA_IDLE) // No GC until a trigger threshold is reached
            if (_gc_page_count >= _gc_stage_count) {
                atomic_store(&_gc_stage, _FSA_ZERO_FLAGS);
            } else {
                atomic_store(&_gc_stage, _FSA_IDLE);
            }
        _FSA_LOCKED_END()

        _FSA_LOCKED(_FSA_ZERO_FLAGS)
            _gc_zero_all_flags(); // Clear all page flags
            atomic_store(&_gc_in_progress, true);
            _thread_reset_iter();
            atomic_store(&_gc_stage, _FSA_MARK_ROOTS);
        _FSA_LOCKED_END()

        _FSA_LOCKED(_FSA_MARK_ROOTS)
            if (_thread_test_iter()) {
                _object_declare_roots(); // After threads have gone through a full cycle, we can start in ernest
                atomic_store(&_gc_stage, _FSA_SCAN_HEAP);
            } else {
                atomic_store(&_gc_stage, _FSA_MARK_ROOTS); // Still waiting
            }
        _FSA_LOCKED_END()

        _FSA_LOCKED(_FSA_SCAN_HEAP)
            bool scan_complete = _gc_scan_heap();
            atomic_store(&_gc_stage, scan_complete
                ? _FSA_PRUNE_HEAP    // Finished
                : _FSA_SCAN_HEAP);   // After a short delay, scan some more
        _FSA_LOCKED_END()

        _FSA_LOCKED(_FSA_PRUNE_HEAP)
            bool prune_complete = _gc_prune_heap();
            if (prune_complete) {
                _gc_stage_count = _gc_page_count + (_gc_page_count < 16 ? 16 : _gc_page_count/2);
                atomic_store(&_gc_stage, _FSA_IDLE); // Wait for the next GC trigger
                atomic_store(&_gc_in_progress, false);
            } else {
                atomic_store(&_gc_stage, _FSA_PRUNE_HEAP); // More pruning
            }
        _FSA_LOCKED_END()
    }
}





