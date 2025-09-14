
#include "common.h"
#include "yafl.h"
#include <malloc.h>
#include <setjmp.h>


EXPORT void abort_on_vtable_lookup() {
    log_error_and_exit("Aborting due to vtable lookup issue", stderr);
}

EXPORT void abort_on_too_large_object() {
    log_error_and_exit("Aborting due to unsupported object size failure", stderr);
}

EXPORT void abort_on_heap_allocation_on_non_worker_thread() {
    log_error_and_exit("Aborting due to attempted allocation on uninitialised thread", stderr);
}




typedef uintptr_t gc_mask_bits_t;
enum { GC_MASK_SIZE = sizeof(gc_mask_bits_t) * 8 };
enum { GC_SLOT_SIZE = 32 };

typedef struct gc_bitmap {
    gc_mask_bits_t a[GC_PAGE_SIZE / GC_SLOT_SIZE / 8 / sizeof(gc_mask_bits_t)];
} __attribute__((aligned(GC_PAGE_SIZE / GC_SLOT_SIZE / 8))) gc_bitmap_t;

typedef struct gc_slot {
    uintptr_t a[GC_SLOT_SIZE / sizeof(uintptr_t)];
} __attribute__((aligned(GC_SLOT_SIZE))) gc_slot_t;

typedef struct gc_page_head {
    struct gc_page*      next;
    size_t         page_count;
    bool             released;
    bool    gc_scan_candidate;
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


static void _bitmap_reset_all(gc_bitmap_t* bitmap) {
    memset(bitmap, 0, sizeof(gc_bitmap_t));
}

static void _bitmap_and(gc_bitmap_t* target, gc_bitmap_t* source) {
    for (int index = 0; index < sizeof(gc_bitmap_t)/sizeof(uintptr_t); ++index)
        target->a[index] &= source->a[index];
}

static void _bitmap_andnot(gc_bitmap_t* target, gc_bitmap_t* source) {
    for (int index = 0; index < sizeof(gc_bitmap_t)/sizeof(uintptr_t); ++index)
        target->a[index] &= ~source->a[index];
}

static bool _bitmap_test_any(gc_bitmap_t* bitmap) {
    for (int index = 0; index < sizeof(gc_bitmap_t)/sizeof(uintptr_t); ++index)
        if (bitmap->a[index])
            return true;
    return false;
}

static bool _bitmap_test(gc_bitmap_t* bitmap, ptrdiff_t bit) {
    return (bitmap->a[bit / GC_MASK_SIZE] & (((gc_mask_bits_t)1) << (bit % GC_MASK_SIZE))) != 0;
}

static void _bitmap_set(gc_bitmap_t* bitmap, ptrdiff_t bit) {
    atomic_fetch_or((_Atomic(gc_mask_bits_t)*)&bitmap->a[bit / GC_MASK_SIZE], ((gc_mask_bits_t)1) << (bit % GC_MASK_SIZE));
}

HIDDEN void _gc_fsa();



enum gc_stage {
    _FSA_LOCKED,

    _FSA_START,
    _FSA_ZERO_FLAGS,    // Write zero to all flags  |
    _FSA_MARK_ROOTS,    // Follow global+thread variables to mark root objects as seen
    _FSA_SCAN_HEAP,     // Scan seen objects on the heap until there are none left to scan
    _FSA_PRUNE_HEAP,    // Remove unused pages from the heap

};

enum action_flag {
    IO_ACTION_NONE,
    IO_ACTION_ACTIVE,       // IO is in progress, so an external thread could scan this thread
    IO_ACTION_SCANNING,     // This thread is currently scanning itself
    IO_ACTION_EXTERNAL_SCAN,// An external thread is scanning this thread's stack

    IO_ACTION_SCAN_REQUEST, // External thread has requested that this thread scan itself
};


/* _gc_stage_count means different things at each stage.
 * At idle, this is the number of pages to have allocated before we start the next gc cycle.
 * At
 */
HIDDEN _Atomic(enum gc_stage) _gc_stage = _FSA_START;
HIDDEN _Atomic(gc_page_t*)_gc_all_pages; // All pages that exist, including recent allocations
HIDDEN _Atomic(bool)    _gc_in_progress;

thread_local struct {
} allocator_struct;

thread_local struct _thread_info {
    struct _thread_info* next;
    bool initialised;

    char*      bump_pointer; // -size to get next object reference
    char*      base_pointer; // until <base_pointer, then we need to ask for more
    gc_page_t* current_page; // Head is current allocation page. Next et-al are full pages waiting for next GC.
    gc_page_t* current_tail; // Tail of that list of pages waiting for next GC.

    _Atomic(enum action_flag) action_flag;
    _Atomic(bool) scan_complete;

    thread_roots_declaration_func_t thread_roots_declaration_func;
    void* thread_roots_context;

    object_t** stack_lower_pointer; // Numerically lower pointer to the stack
    object_t** stack_upper_pointer; // Numerically higher pointer to the stack
    struct { jmp_buf jb; } saved_registers[1]; // Expensive way to save the registers for GC

} _thread_info;
static _Atomic(struct _thread_info*) _threads = ATOMIC_VAR_INIT(NULL);




static void _fillmem(uint32_t* memory, uint32_t value, size_t count) {
    for (size_t index = 0; index < count; ++index) {
        memory[index] = value;
    }
}

HIDDEN gc_page_t* _gc_page_alloc(size_t page_count) {
    gc_page_t* page = memory_pages_alloc(page_count);
    if (page == NULL)
        abort_on_out_of_memory();

    memset(page, 0, GC_PAGE_SIZE * page_count);
    page->head.page_count = page_count;
    page->head.released = false;
    page->head.gc_scan_candidate = false;

    _gc_fsa();

    return page;
}

HIDDEN void _gc_page_free(gc_page_t** page_ptr) {
    gc_page_t* page = *page_ptr;
    assert(page->head.released == false);
    page->head.released = true;
    *page_ptr = page->head.next;
    memory_pages_free(page, page->head.page_count);
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
    object_gc_mark_as_seen(*object_ptr);
}

HIDDEN void _object_declare_roots() {
    declare_roots_thread(_object_declare_root);
    _declare_roots_yafl(_object_declare_root);
}



HIDDEN size_t _object_size(object_t* ptr) {
    size_t size;
    vtable_t* vt = object_get_vtable(ptr);
    if (vt->array_len_offset) {
        uint32_t len = *(uint32_t*)&((char*)ptr)[vt->array_len_offset];
        size = vt->object_size + vt->array_el_size*len;
    } else {
        size = vt->object_size;
    }
    size_t actual_size = (size + sizeof(gc_slot_t) - 1) / sizeof(gc_slot_t) * sizeof(gc_slot_t);
    return actual_size;
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

    if (_thread_info.bump_pointer - _thread_info.base_pointer < actual_size) {
        gc_page_t* new_page = _gc_page_alloc(1);

        _thread_info.base_pointer = (char*)(new_page->slots);
        _thread_info.bump_pointer = (char*)(new_page->slots + GC_SLOTS_PER_PAGE);

        new_page->head.next = NULL;
        if (_thread_info.current_tail) {
            _thread_info.current_tail->head.next = new_page;
            _thread_info.current_tail = new_page;
        } else {
            _thread_info.current_page = new_page;
            _thread_info.current_tail = new_page;
        }

    }

    gc_page_t* page = _thread_info.current_tail;
    gc_slot_t*  ptr = (gc_slot_t*)(_thread_info.bump_pointer -= actual_size);
    ptrdiff_t  slot = ptr - page->slots;
    _bitmap_set(&page->head.object_heads, slot);

    return ptr;
}

INLINE bool _object_is_on_heap(object_t* ptr) {
    return ptr != NULL
        && ((intptr_t)ptr & 3) == 0             // Avoid data packed into the pointer, like small integers and strings.
        && ((intptr_t)ptr->vtable & 3) != 0;    // Avoid static declared objects, because they don't have a heap header.
}



HIDDEN size_t _gc_scan_object_deep(object_t* ptr, size_t depth);

HIDDEN size_t _gc_scan_elements(object_t** ptr, uint32_t pointer_locations, size_t depth) {
    size_t scanned_count = 0;
    for (int index = 0; index < 32; ++index) {
        if (pointer_locations & (1 << index)) {
            scanned_count += _gc_scan_object_deep(ptr[index], depth);
        }
    }
    return scanned_count;
}

HIDDEN bool _is_in_pages_list(gc_page_t* page) {
    for (gc_page_t* ptr = _gc_all_pages; ptr; ptr = ptr->head.next)
        if (ptr == page)
            return true;
    return false;
}

HIDDEN size_t _gc_scan_object_deep(object_t* ptr, size_t depth) {
    if (!_object_is_on_heap(ptr)) {
        return 0;
    }

    gc_page_t* page; ptrdiff_t slot;
    _object_get_page_and_slot(ptr, &page, &slot);
    if (!page->head.gc_scan_candidate) {
        return 0;
    }

    assert(_bitmap_test(&page->head.object_heads, slot));
    if (_bitmap_test(&page->head.marks_scanned, slot)) {
        return 0;
    }

    _bitmap_set(&page->head.marks_seen, slot);
    if (depth == 0) {
        return 0;
    }

    vtable_t* vt = object_get_vtable(ptr);
    size_t scanned_count = 1;
    depth -= 1;

    _bitmap_set(&page->head.marks_scanned, slot);

    if (vt->object_pointer_locations) {
        size_t count = _gc_scan_elements((object_t**)ptr, vt->object_pointer_locations, depth);
        scanned_count += count;
    }

    if (vt->array_el_pointer_locations) {
        uint32_t len = *(uint32_t*)&((char*)ptr)[vt->array_len_offset];
        char*  array = ((char*)ptr) + vt->object_size;
        for (; len-- > 0; array += vt->array_el_size) {
            size_t count = _gc_scan_elements((object_t**)array, vt->array_el_pointer_locations, depth);
            scanned_count += count;
        }
    }

    return scanned_count;
}

HIDDEN size_t _gc_scan_object_shallow(object_t* ptr) {
    return _gc_scan_object_deep(ptr, 1);
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





HIDDEN bool _set_action_flag(struct _thread_info* thread, enum action_flag expected, enum action_flag requested) {
    return atomic_compare_exchange_strong(&thread->action_flag, &expected, requested);
}

HIDDEN bool _is_object_head(gc_slot_t* ptr) {
    gc_page_t* page = (gc_page_t*)((uintptr_t)ptr &~ (GC_PAGE_SIZE-1));
    ptrdiff_t slot = ptr - page->slots;
    return slot >= 0 && slot < GC_SLOTS_PER_PAGE && _bitmap_test(&page->head.object_heads, slot);
}

HIDDEN bool _gc_pointer_is_into_heap(gc_slot_t* ptr) {
    return ptr != NULL
        && ((intptr_t)ptr & (GC_SLOT_SIZE-1)) == 0
        && memory_pages_is_heap(ptr)
        && _is_object_head(ptr);
        // for (gc_page_t* page = _all_pages; page != NULL; page = page->head.next) {
        //     ptrdiff_t slot = ptr - page->slots;
        //     if (slot >= 0 && slot < GC_SLOTS_PER_PAGE && _bitmap_test(&page->head.object_heads, slot)) {
        //         return true;
        //     }
        // }
}

HIDDEN void _gc_scan_range(object_t** range_ptr, object_t** range_end) {
    for (; range_ptr != range_end; range_ptr++) {
        object_t* ptr = *range_ptr;
        if (_gc_pointer_is_into_heap((gc_slot_t*)ptr)) {
            object_gc_mark_as_seen(ptr);
        }
    }
}

HIDDEN void _gc_scan_stack(struct _thread_info* thread) {
    // This is either called from the owning thread, or from a context where we guarentee that the
    // target thread is suspended, so we are free to mess around with the stack and thread locals.

    // Scan stack and registers
    _gc_scan_range(thread->stack_lower_pointer, thread->stack_upper_pointer);
    _gc_scan_range((object_t**)&thread->saved_registers[0], (object_t**)&thread->saved_registers[1]);

    // Any current thread private pages are moved into the global heap for GC processing
    if (thread->current_page) {
        for (gc_page_t* page = thread->current_page; page; page = page->head.next)
            page->head.gc_scan_candidate = true;

        thread->current_tail->head.next = _gc_all_pages;
        while (!atomic_compare_exchange_weak(&_gc_all_pages, &thread->current_tail->head.next, thread->current_page));
        thread->current_page = thread->current_tail = NULL;
        thread->base_pointer = thread->bump_pointer = NULL;
    }

    // Thread library has some stuff
    thread->thread_roots_declaration_func(thread->thread_roots_context, _object_declare_root);

    atomic_store(&thread->scan_complete, true);
}

EXPORT void object_gc_mark_as_seen(object_t* ptr) {
    if (ptr != NULL && _object_is_on_heap(ptr)) {
        gc_page_t* page; ptrdiff_t slot;
        _object_get_page_and_slot(ptr, &page, &slot);
        assert(_bitmap_test(&page->head.object_heads, slot));
        _bitmap_set(&page->head.marks_seen, slot);
    }
}

static void donothing() {

}

EXPORT object_t* object_gc_mutation(object_t* ptr) {
    if (_gc_in_progress && _object_is_on_heap(ptr)) {
        gc_page_t* page; ptrdiff_t slot;
        _object_get_page_and_slot(ptr, &page, &slot);
        if (page->head.gc_scan_candidate && !_bitmap_test(&page->head.marks_scanned, slot)) {
            object_gc_mark_as_seen(ptr);
            _gc_scan_object_shallow(ptr);
        }
    }
    return ptr;
}

// Start of potentially thread pausing IO
EXTERN void object_gc_io_begin() {
    for (;;) {
        assert(atomic_load(&_thread_info.action_flag) == IO_ACTION_NONE
            || atomic_load(&_thread_info.action_flag) == IO_ACTION_SCAN_REQUEST);

        switch (atomic_load(&_thread_info.action_flag)) {
            case IO_ACTION_NONE: {
                object_t* some_random_var = NULL;
#ifdef STACK_GROWS_DOWN
                _thread_info.stack_lower_pointer = &some_random_var;
#else
                _thread_info.stack_upper_pointer = &some_random_var;
#endif
                setjmp(_thread_info.saved_registers[0].jb);

                if (_set_action_flag(&_thread_info, IO_ACTION_NONE, IO_ACTION_ACTIVE)) {
                    return;
                }
            } break;

            case IO_ACTION_SCAN_REQUEST:
                object_gc_safe_point();
                break;

            default:
                break;
        }
    }
}

// End of potentially thread pausing IO
EXTERN void object_gc_io_end() {
    enum action_flag expected;
    struct _thread_info* thread = &_thread_info;
    do {assert(atomic_load(&thread->action_flag) == IO_ACTION_ACTIVE
            || atomic_load(&thread->action_flag) == IO_ACTION_EXTERNAL_SCAN);

        expected = IO_ACTION_ACTIVE;
    } while (!atomic_compare_exchange_weak(&thread->action_flag, &expected, IO_ACTION_NONE));
}

HIDDEN NOINLINE void _gc_scan_this_threads_stack() {
    struct _thread_info* thread = &_thread_info;

    object_t* some_random_var = NULL;
#ifdef STACK_GROWS_DOWN
    thread->stack_lower_pointer = &some_random_var;
#else
    thread->stack_upper_pointer = &some_random_var;
#endif

    setjmp(thread->saved_registers[0].jb);
    _gc_scan_stack(thread);
}

// Arbitary safe point for GC magic to happen
EXTERN void object_gc_safe_point() {
    if (_set_action_flag(&_thread_info, IO_ACTION_SCAN_REQUEST, IO_ACTION_SCANNING)) {
        _gc_scan_this_threads_stack();
        atomic_store(&_thread_info.action_flag, IO_ACTION_NONE);
    }
}

// Any thread that can do allocation must call this early on
EXTERN void object_gc_declare_thread(thread_roots_declaration_func_t thread_roots_declaration_func, void*thread_roots_context) {
    object_t* some_random_var = NULL;
#ifdef STACK_GROWS_DOWN
    _thread_info.stack_upper_pointer = &some_random_var;
#else
    _thread_info.stack_lower_pointer = &some_random_var;
#endif

    _thread_info.thread_roots_declaration_func = thread_roots_declaration_func;
    _thread_info.thread_roots_context = thread_roots_context;

    _thread_info.next = &_thread_info;
    _thread_info.action_flag = IO_ACTION_NONE;
    while (!atomic_compare_exchange_weak(&_threads, &_thread_info.next, &_thread_info));

    _thread_info.initialised = true;
}

HIDDEN void _gc_start_thread_scanning() {
    for (struct _thread_info* thread = _threads; thread != NULL; thread = thread->next) {
        atomic_store(&thread->scan_complete, false);
    }

    _gc_scan_this_threads_stack();
}

HIDDEN bool _gc_complete_thread_scanning() {
    object_gc_safe_point();

    for (struct _thread_info* thread = _threads; thread != NULL; thread = thread->next) {
        if (atomic_load(&thread->scan_complete) == false) {

            enum action_flag flag = thread->action_flag;
            switch (flag) {
                case IO_ACTION_NONE: { // Ask the thread to scan its own stack
                    enum action_flag expected = IO_ACTION_NONE;
                    atomic_compare_exchange_strong(&thread->action_flag, &expected, IO_ACTION_SCAN_REQUEST);
                } break;

                case IO_ACTION_ACTIVE: { // We scan the thread's stack
                    enum action_flag expected = IO_ACTION_ACTIVE;
                    if (atomic_compare_exchange_strong(&thread->action_flag, &expected, IO_ACTION_EXTERNAL_SCAN)) {
                        _gc_scan_stack(thread); // Scan, blocking object_gc_io_end()
                        atomic_store(&thread->action_flag, IO_ACTION_ACTIVE);
                    }
                } break;

                default:
                    break;
            }

            return false;
        }
    }
    return true;
}









HIDDEN size_t _gc_scan_page(gc_page_t* page) {
    size_t scanned_object_count = 0;
    for (ptrdiff_t index = sizeof(gc_bitmap_t) / sizeof(gc_mask_bits_t); --index >= 0; ) {
        assert( (page->head.marks_scanned.a[index] &~ page->head.marks_seen.a[index]) == 0 );
        assert( (page->head.marks_seen.a[index] &~ page->head.object_heads.a[index]) == 0 );

        gc_mask_bits_t masked = page->head.marks_seen.a[index] &~ page->head.marks_scanned.a[index];
        if (masked) {
            int counted = __builtin_ctzll(masked);
            int mask_size = GC_MASK_SIZE;
            ptrdiff_t slot = index * mask_size + counted;

            assert(_bitmap_test(&page->head.object_heads, slot));

            size_t count = _gc_scan_object_deep((object_t*)&page->slots[slot], 100);
            scanned_object_count += count;
        }
    }
    return scanned_object_count;
}


static size_t _gc_scan_heap_repeats = 0;
static size_t _gc_scan_heap_object_count = 0;
static gc_page_t* _gc_scan_heap_progress = NULL;
HIDDEN bool _gc_scan_heap() {
    size_t page_limit = 200;

    do {
        if (_gc_scan_heap_progress == NULL) {
            _gc_scan_heap_repeats++;
            _gc_scan_heap_object_count = 0;
            _gc_scan_heap_progress = _gc_all_pages;
        }

        for (; _gc_scan_heap_progress != NULL; _gc_scan_heap_progress = _gc_scan_heap_progress->head.next) {
            size_t count = _gc_scan_page(_gc_scan_heap_progress);
            _gc_scan_heap_object_count += count;

            if (--page_limit == 0)
                return false; // Early exit, call again
        }

        // We get here because _gc_scan_heap_progress is NULL, which is the start condition for the next cycle.
    } while (_gc_scan_heap_object_count > 0);

    return true;
}

static gc_page_t* _gc_prune_heap_progress = NULL;
HIDDEN bool _gc_prune_heap() {
    int max_iter_count = 100;

    if (_gc_prune_heap_progress == NULL) {
        _gc_prune_heap_progress = _gc_all_pages;
    }

    // Never prune the first page, because multiple threads are updating '_all_pages' so
    // we can't safely update it to point to the following page. That would be an A-B-A
    // issue. However, page->head.next is never updated by multiple threads, so removing
    // any of the following pages from a locked context is safe.

    while (_gc_prune_heap_progress->head.next != NULL) {
        gc_page_t* page = _gc_prune_heap_progress->head.next;

#ifndef NDEBUG
        gc_bitmap_t test = page->head.marks_seen;
        _bitmap_andnot(&test, &page->head.object_heads);
        assert(!_bitmap_test_any(&test));
#endif

        if (_bitmap_test_any(&page->head.marks_seen)) { // Something is still seen on the page, so it remains live
            // Move forward by one
            _gc_prune_heap_progress = page;

            // Un-mark objects that no longer exist
            _bitmap_and(&page->head.object_heads, &page->head.marks_seen);

#ifndef NDEBUG
            ptrdiff_t counter = 0;
            for (ptrdiff_t slot = 0; slot < GC_SLOTS_PER_PAGE; ++slot) {
                if (_bitmap_test(&page->head.object_heads, slot)) {
                    object_t* obj = (object_t*)&page->slots[slot];
                    size_t size = _object_size(obj);
                    counter = size / sizeof(gc_slot_t);
                    assert(counter > 0);
                }
                if (--counter < 0) {
                    // Fill unused space to cause crashes if GC gets it wrong
                    _fillmem((uint32_t*)&page->slots[slot], 0xdeadbeef, sizeof(gc_slot_t) / sizeof(uint32_t));
                }
            }
#endif

        } else {

#ifndef NDEBUG
            // We're about to release this page. Just in-case some pointer still exists, fill it with rubbish, to cause a crash.
            _fillmem((uint32_t*)page->slots, 0xdeadbeef, GC_SLOTS_PER_PAGE * sizeof(gc_slot_t) / sizeof(uint32_t));
#endif
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
    for (gc_page_t* page = _gc_all_pages; page != NULL; page = page->head.next) {
        _bitmap_reset_all(&page->head.marks_seen);
        _bitmap_reset_all(&page->head.marks_scanned);
    }
}

#define _FSA_LOCKED(original_state)\
    case original_state:{\
        enum gc_stage _fsa_state_expected = original_state;\
        if (atomic_compare_exchange_strong(&_gc_stage, &_fsa_state_expected, _FSA_LOCKED)) {\

#define _FSA_LOCKED_END()\
        }\
    } break;

HIDDEN void _gc_fsa() {
    switch (_gc_stage) {
        case _FSA_LOCKED: // Another thread holds a lock
            break;

        _FSA_LOCKED(_FSA_START)
            atomic_store(&_gc_stage, _FSA_ZERO_FLAGS);
        _FSA_LOCKED_END()

        _FSA_LOCKED(_FSA_ZERO_FLAGS)
            _gc_scan_heap_repeats = 0;
            _gc_zero_all_flags(); // Clear all page flags
            atomic_store(&_gc_in_progress, true);
            _gc_start_thread_scanning();
            atomic_store(&_gc_stage, _FSA_MARK_ROOTS);
        _FSA_LOCKED_END()

        _FSA_LOCKED(_FSA_MARK_ROOTS)
            if (_gc_complete_thread_scanning()) {
                _object_declare_roots(); // After threads have been scanned, we can start in ernest
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
            // fprintf(stderr, "Scanned heap %ld times\n", _gc_scan_heap_repeats);
            bool prune_complete = _gc_prune_heap();
            if (prune_complete) {
                atomic_store(&_gc_stage, _FSA_START); // Wait for the next GC trigger
                atomic_store(&_gc_in_progress, false);
            } else {
                atomic_store(&_gc_stage, _FSA_PRUNE_HEAP); // More pruning
            }
        _FSA_LOCKED_END()
    }
}





