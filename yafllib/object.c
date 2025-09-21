
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
    _Atomic(struct gc_page*) next;
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
    _FSA_SCAN_IN_PROGRESS, //

    _FSA_PRUNE_HEAP,    // Remove unused pages from the heap
    _FSA_PRUNE_IN_PROGRESS,

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
HIDDEN _Atomic(bool)    _gc_in_progress;

HIDDEN _Atomic(gc_page_t*)  _gc_all_pages_head; // All pages that exist, including recent allocations
HIDDEN _Atomic(gc_page_t*)* _gc_all_pages_tail = &_gc_all_pages_head;


thread_local struct _thread_info {
    struct _thread_info* next;
    bool initialised;

    char*      bump_pointer; // -size to get next object reference
    char*      base_pointer; // until <base_pointer, then we need to ask for more
    gc_page_t* current_page;
    gc_page_t* current_tail;

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
    _gc_fsa();

    gc_page_t* page = memory_pages_alloc(page_count);
    if (page == NULL)
        abort_on_out_of_memory();

    memset(page, 0, GC_PAGE_SIZE * page_count);
    page->head.page_count = page_count;
    page->head.released = false;
    page->head.gc_scan_candidate = false;

    return page;
}

HIDDEN void _gc_page_free(gc_page_t* page) {
    assert(page->head.released == false);
    page->head.released = true;
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





static void _gc_scan_elements(object_t** ptr, uint32_t pointer_locations) {
    for (int index = 0; index < 32; ++index) {
        if (pointer_locations & (1 << index)) {
            object_gc_mark_as_seen(ptr[index]);
        }
    }
}

HIDDEN void _gc_scan_object_meat(object_t* ptr) {
    vtable_t* vt = object_get_vtable(ptr);

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
}

HIDDEN void _gc_scan_object_shallow(object_t* ptr) {
    if (!_object_is_on_heap(ptr)) {
        return;
    }

    gc_page_t* page; ptrdiff_t slot;
    _object_get_page_and_slot(ptr, &page, &slot);
    if (!page->head.gc_scan_candidate) {
        return;
    }

    assert(_bitmap_test(&page->head.object_heads, slot));

    _gc_scan_object_meat(ptr);

    // This must only be set after scanning is complete, otherwise a call to object_gc_mutation
    // from another thread can possibly fail to scan and mutate the pointer before this scan
    // completes.
    _bitmap_set(&page->head.marks_scanned, slot);
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
}

HIDDEN void _gc_scan_range(object_t** range_ptr, object_t** range_end) {
    for (; range_ptr != range_end; range_ptr++) {
        object_t* ptr = *range_ptr;
        if (_gc_pointer_is_into_heap((gc_slot_t*)ptr)) {
            object_gc_mark_as_seen(ptr);
        }
    }
}

static size_t _gc_count_of_pages_at_start_of_scan;
HIDDEN void _gc_scan_stack(struct _thread_info* thread) {
    // This is either called from the owning thread, or from a context where we guarentee that the
    // target thread is suspended, so we are free to mess around with the stack and thread locals.

    // Scan stack and registers
    _gc_scan_range(thread->stack_lower_pointer, thread->stack_upper_pointer);
    _gc_scan_range((object_t**)&thread->saved_registers[0], (object_t**)&thread->saved_registers[1]);

    // Any current thread private pages are moved into the global heap for GC processing
    for (gc_page_t *next = thread->current_page, *page; (page = next) != NULL; ) {
        page->head.gc_scan_candidate = true;
        next = page->head.next;

        page->head.next = NULL;
        gc_page_t *expected;
        do {expected = NULL;
        } while (!atomic_compare_exchange_strong(_gc_all_pages_tail, &expected, page));
        _gc_all_pages_tail = &page->head.next;
        _gc_count_of_pages_at_start_of_scan += 1;
    }

    thread->current_page = thread->current_tail = NULL;
    thread->base_pointer = thread->bump_pointer = NULL;

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
    if (_gc_in_progress) {
        _gc_scan_object_meat(ptr);
        // gc_page_t* page; ptrdiff_t slot;
        // _object_get_page_and_slot(ptr, &page, &slot);
        // if (page->head.gc_scan_candidate && !_bitmap_test(&page->head.marks_scanned, slot)) {
        //     object_gc_mark_as_seen(ptr);
        //     _gc_scan_object_shallow(ptr);
        // }
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









HIDDEN bool _gc_scan_page(gc_page_t* page) {
    bool didSome = false;
    for (ptrdiff_t index = 0; index < sizeof(gc_bitmap_t) / sizeof(gc_mask_bits_t); ++index) {
        assert( (page->head.marks_scanned.a[index] &~ page->head.marks_seen.a[index]) == 0 );
        assert( (page->head.marks_seen.a[index] &~ page->head.object_heads.a[index]) == 0 );

        gc_mask_bits_t candidate_bits = page->head.marks_seen.a[index] &~ page->head.marks_scanned.a[index];
        if (candidate_bits != 0) {
            int low_zeros_count = __builtin_ctzll(candidate_bits);
            ptrdiff_t slot = index * GC_MASK_SIZE + low_zeros_count;

            assert(_bitmap_test(&page->head.object_heads, slot));

            _gc_scan_object_shallow((object_t*)&page->slots[slot]);

            didSome = true;
            index = -1; // Loop increment will bring it to 0
        }
    }
    return didSome;
}


static _Atomic(size_t) _gc_scan_heap_countdown;
static _Atomic(gc_page_t*) _gc_scan_heap_progress;
static _Atomic(bool) _gc_scan_heap_did_some_work;

static size_t _gc_scan_heap_repeats = 0;

HIDDEN bool _gc_scan_heap() {
    gc_page_t *page = _gc_scan_heap_progress;

    do {
        if (page == NULL)
            return false;
    } while (!atomic_compare_exchange_weak(&_gc_scan_heap_progress, &page, page->head.next));

    if (_gc_scan_page(page))
        _gc_scan_heap_did_some_work = true;

    return atomic_fetch_sub(&_gc_scan_heap_countdown, 1) == 1;
}

static _Atomic(size_t) _gc_count_of_pages_at_end_of_scan = 0;
static _Atomic(_Atomic(gc_page_t*)*) _gc_prune_progress;
static _Atomic(size_t) _gc_prune_count_of_used_slots;

HIDDEN bool _gc_prune_heap() {
    for (;;) {
        _Atomic(gc_page_t*) *prev_ptr = atomic_load(&_gc_prune_progress);
        if (prev_ptr == NULL) {
            return false; // Some other thread was the final call
        }

        gc_page_t *page = atomic_load(prev_ptr);

        if (page == NULL) {
            _Atomic(gc_page_t*)* expected = prev_ptr;
            if (atomic_compare_exchange_strong(&_gc_prune_progress, &expected, NULL)) {
                return true; // Final call
            }

        } else if (((uintptr_t)page & 1) != 0) {
            // Some other thread is in the process of removing this page. This thread needs to go around again.
            // So...  do nothing

        } else if (_bitmap_test_any(&page->head.marks_seen)) {
            // Attempt to move pointer. Extra work is done if we are the thread that succeeds.
            if (atomic_compare_exchange_strong(&_gc_prune_progress, &prev_ptr, &page->head.next)) {
                // We need to keep a count of pages
                atomic_fetch_add(&_gc_count_of_pages_at_end_of_scan, 1);
#ifndef NDEBUG
                gc_bitmap_t test = page->head.marks_seen;
                _bitmap_andnot(&test, &page->head.object_heads);
                assert(!_bitmap_test_any(&test));
#endif
                // Un-mark objects that no longer exist
                _bitmap_and(&page->head.object_heads, &page->head.marks_seen);
#ifndef NDEBUG
                ptrdiff_t counter = 0;
                size_t used_slots = 0;
                for (ptrdiff_t slot = 0; slot < GC_SLOTS_PER_PAGE; ++slot) {
                    if (_bitmap_test(&page->head.object_heads, slot)) {
                        object_t* obj = (object_t*)&page->slots[slot];
                        size_t size = _object_size(obj);
                        used_slots += size;
                        counter = size / sizeof(gc_slot_t);
                        assert(counter > 0);
                    }
                    if (--counter < 0) {
                        // Fill unused space to cause crashes if GC gets it wrong
                        _fillmem((uint32_t*)&page->slots[slot], 0xdeadbeef, sizeof(gc_slot_t) / sizeof(uint32_t));
                    }
                }
                atomic_fetch_add(&_gc_prune_count_of_used_slots, used_slots / sizeof(gc_slot_t));
#endif
            }

        } else {
            // Mark the pointer so that no other thread will attempt to access this page
            gc_page_t *expected = page;
            gc_page_t *requested = (gc_page_t*)((uintptr_t)page | 1);
            if (atomic_compare_exchange_strong(prev_ptr, &expected, requested)) {
                // If this is the last node, skip it, as releasing it means having to update the tail pointer
                // which, when you really really think about it, ends up being very complicated.
                if (page->head.next == NULL) {
                    // Untag the pointer, move along and let the loop swing around
                    atomic_store(prev_ptr, page);
                    atomic_store(&_gc_prune_progress, &page->head.next);

                } else {
                    // Unlink this node. Marked pointer ensures that we aren't contending with other threads.
                    atomic_store(prev_ptr, page->head.next);
    #ifndef NDEBUG
                    // We're about to release this page. Just in-case some pointer still exists, fill it with rubbish, to cause a crash.
                    _fillmem((uint32_t*)page->slots, 0xdeadbeef, GC_SLOTS_PER_PAGE * sizeof(gc_slot_t) / sizeof(uint32_t));
    #endif
                    _gc_page_free(page);
                    return false; // Not the final call
                }
            }
        }
    }
}


HIDDEN void _gc_zero_all_flags() {
    _gc_count_of_pages_at_start_of_scan = 0;
    for (gc_page_t* page = _gc_all_pages_head; page != NULL; page = page->head.next) {
        _bitmap_reset_all(&page->head.marks_seen);
        _bitmap_reset_all(&page->head.marks_scanned);
        _gc_count_of_pages_at_start_of_scan += 1;
    }
}

#define _FSA_LOCKED(original_state)\
    case original_state:{\
        enum gc_stage _fsa_state_expected = original_state;\
        locked_by_stage = original_state;\
        if (atomic_compare_exchange_strong(&_gc_stage, &_fsa_state_expected, _FSA_LOCKED)) {\

#define _FSA_LOCKED_END()\
        }\
    } break;

static size_t locked_count_zero = 0;
static size_t locked_count_mark = 0;
static size_t locked_count_prune = 0;
static enum gc_stage locked_by_stage;

HIDDEN void _gc_fsa() {
    switch (_gc_stage) {
        case _FSA_LOCKED: // Another thread holds a lock
            switch (locked_by_stage) {
                case _FSA_ZERO_FLAGS:
                    locked_count_zero++;
                    break;
                case _FSA_MARK_ROOTS:
                    locked_count_mark++;
                    break;
                case _FSA_PRUNE_HEAP:
                    locked_count_prune++;
                    break;
                default:
                    break;
            }
            break;

        _FSA_LOCKED(_FSA_START)
            locked_count_zero = 0;
            locked_count_mark = 0;
            locked_count_prune = 0;
            // TODO: Add some start condition here
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
                _gc_scan_heap_repeats = 0;
                _gc_scan_heap_did_some_work = true;
                atomic_store(&_gc_stage, _FSA_SCAN_HEAP);
            } else {
                atomic_store(&_gc_stage, _FSA_MARK_ROOTS); // Still waiting
            }
        _FSA_LOCKED_END()

        _FSA_LOCKED(_FSA_SCAN_HEAP)
            if (_gc_all_pages_head && _gc_scan_heap_did_some_work) {
                _gc_scan_heap_repeats += 1;
                _gc_scan_heap_countdown = _gc_count_of_pages_at_start_of_scan;
                _gc_scan_heap_progress = _gc_all_pages_head;
                _gc_scan_heap_did_some_work = false;
                atomic_store(&_gc_stage, _FSA_SCAN_IN_PROGRESS);
            } else {
                atomic_store(&_gc_stage, _FSA_PRUNE_HEAP);
            }
        _FSA_LOCKED_END()

        case _FSA_SCAN_IN_PROGRESS:
            for (size_t count = 8 * _gc_scan_heap_repeats; count != 0; --count) {
                if (_gc_scan_heap()) {
                    // Was the final one, so we need to do something
                    atomic_store(&_gc_stage, _FSA_SCAN_HEAP);
                    break;
                }
            }
            break;

        _FSA_LOCKED(_FSA_PRUNE_HEAP)
            _gc_prune_progress = &_gc_all_pages_head;
            _gc_count_of_pages_at_end_of_scan = 0;
            _gc_prune_count_of_used_slots = 0;
            atomic_store(&_gc_stage, _FSA_PRUNE_IN_PROGRESS); // Wait for the next GC trigger
        _FSA_LOCKED_END()

        case _FSA_PRUNE_IN_PROGRESS:
            for (size_t count = 8 * _gc_scan_heap_repeats; count != 0; --count) {
                if (_gc_prune_heap()) {
                    // Was the final one, so we need to do something
#ifndef NDEBUG
                    double used_percent = _gc_prune_count_of_used_slots * 100.0 / (_gc_count_of_pages_at_end_of_scan * GC_SLOTS_PER_PAGE);
                    fprintf(stderr,
                            "Scanned heap %ld times, locked_count_zero = %ld, locked_count_mark = %ld, locked_count_prune = %ld, "
                            "heap_count = %ld / %ld, used_percent = %.2f%%\n",
                            _gc_scan_heap_repeats, locked_count_zero, locked_count_mark, locked_count_prune,
                            _gc_count_of_pages_at_end_of_scan, _gc_count_of_pages_at_start_of_scan, used_percent);
#endif
                    atomic_store(&_gc_in_progress, false);
                    atomic_store(&_gc_stage, _FSA_START);
                    break;
                }
            }
            break;
    }
}

EXPORT void object_gc_init() {
}




