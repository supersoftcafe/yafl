
#include "common.h"
#include "yafl.h"
#include <malloc.h>


EXPORT void abort_on_vtable_lookup() {
    log_error_and_exit("Aborting due to vtable lookup issue", stderr);
}

EXPORT void abort_on_out_of_memory() {
    fputs("Aborting due to memory allocation failure", stderr);
}

EXPORT void abort_on_too_large_object() {
    fputs("Aborting due to unsupported object size failure", stderr);
}

EXPORT void abort_on_heap_allocation_on_non_worker_thread() {
    fputs("Aborting due to attempted allocation on uninitialised thread", stderr);
}


typedef struct gc_page_slot {
    uint32_t lumpy_stuff;
} ALIGNED gc_page_slot_t;


typedef struct gc_page {
    uint8_t marks[512-16];
    struct gc_page* all_pages_next;
    gc_page_slot_t slots[512-16];
} gc_page_t;

static_assert(sizeof(gc_page_t) == 16384, "Page size doesn't add up");


enum { MAX_OBJECT_SIZE = sizeof(gc_page_t) - offsetof(gc_page_t, slots[0]) };



HIDDEN bool _marking_in_progress = false;

thread_local struct {
    char* bump_pointer; // -size to get next object reference
    char* base_pointer; // until <base_pointer, then we need to ask for more
    gc_page_t* new_page_pool_ptr; // a block of many pages available to this thread
    ptrdiff_t new_page_pool_count; // how many pages remain in the block
    gc_page_t* all_pages; // all pages created by this thread, not owned by this thread
    bool initialised;
} allocator_struct;


EXTERN void _object_get_page_and_slot(object_t* ptr, gc_page_t** page_out, ptrdiff_t* slot_out) {
    *page_out = (gc_page_t*)((intptr_t)ptr & ~(sizeof(gc_page_t)-1));
    *slot_out = (gc_page_slot_t*)ptr - (*page_out)->slots;
}


static void default_roots_declaration_func(void(*declare)(object_t**)) { }
HIDDEN roots_declaration_func_t _declare_roots_yafl = default_roots_declaration_func;
EXTERN roots_declaration_func_t add_roots_declaration_func(roots_declaration_func_t f) {
    roots_declaration_func_t previous = _declare_roots_yafl;
    _declare_roots_yafl = f;
    return previous;
}

HIDDEN void _object_declare_roots(void(*declare)(object_t**)) {
    declare_roots_thread(declare);
    _declare_roots_yafl(declare);
}

HIDDEN void _object_bulk_alloc_new_pages() {
    if (!allocator_struct.initialised) {
        abort_on_heap_allocation_on_non_worker_thread();
    }

    ptrdiff_t count = 256;
    gc_page_t* ptr = memalign(sizeof(gc_page_t), sizeof(gc_page_t)*count);
    if (!ptr) {
        abort_on_out_of_memory();
    }

    memset(ptr, 0, sizeof(gc_page_t)*count);
    allocator_struct.new_page_pool_ptr = ptr;
    allocator_struct.new_page_pool_count = count;
}

HIDDEN void* _object_alloc2(size_t size) {
    if (size > MAX_OBJECT_SIZE) {
        // TODO: Support larger objects as multiples of page size
        abort_on_too_large_object();
    }

    size_t actual_size = (size + sizeof(gc_page_slot_t) - 1) / sizeof(gc_page_slot_t) * sizeof(gc_page_slot_t);

    if (allocator_struct.new_page_pool_count == 0) {
        _object_bulk_alloc_new_pages();
    }

    gc_page_t* page = allocator_struct.new_page_pool_ptr;
    allocator_struct.new_page_pool_count -= 1;
    allocator_struct.new_page_pool_ptr += 1;
    page->all_pages_next = allocator_struct.all_pages;
    allocator_struct.all_pages = page;

    if (actual_size > MAX_OBJECT_SIZE / 2) {
        // Dedicate a page without replacing the bump pointer
        return (char*)(page + 1) - actual_size;
    } else {
        // Give page to bump pointer and take some memory to return
        allocator_struct.base_pointer = (char*)page->slots;
        allocator_struct.bump_pointer = (char*)(page + 1) - actual_size;
        return allocator_struct.bump_pointer;
    }
}

HIDDEN void* _object_alloc(size_t size) {
    size_t actual_size = (size + sizeof(gc_page_slot_t) - 1) / sizeof(gc_page_slot_t) * sizeof(gc_page_slot_t);

    // size_t remainder = (sizeof(gc_page_t)-1) & (intptr_t)allocator_struct.bump_pointer;
    // if (unlikely(actual_size) > remainder) {
    //     return _object_alloc2(size);
    // } else {
    //     return allocator_struct.bump_pointer -= actual_size;
    // }

    char* new_pointer = allocator_struct.bump_pointer - actual_size;
    allocator_struct.bump_pointer = new_pointer;
    ptrdiff_t remainder = new_pointer - allocator_struct.base_pointer;
    if (LIKELY(remainder >= 0)) {
        return new_pointer;
    } else {
        return _object_alloc2(size);
    }
}

HIDDEN void _object_scan(object_t* ptr) {
    // TODO: Add scanning code
    gc_page_t* page; ptrdiff_t slot;
    _object_get_page_and_slot(ptr, &page, &slot);
    page->marks[slot] = 3;
}

HIDDEN bool _object_page_scan(gc_page_t* page) {
    bool result = false;
    for (int slot = 0; slot < sizeof(page->marks); ++slot) {
        if (UNLIKELY(page->marks[slot] == 1)) {
            _object_scan((object_t*)&page->slots[slot]);
            result = true;
        }
    }
    return result;
}

INLINE bool _object_is_on_heap(object_t* ptr) {
    return ((intptr_t)ptr & 3) == 0             // Avoid data packed into the pointer, like small integers and strings.
        && ((intptr_t)ptr->vtable & 3) != 0;    // Avoid static declared objects, because they don't have a heap header.
}

INLINE void _object_mark_as_seen(object_t* ptr) {
    if (ptr != NULL && _object_is_on_heap(ptr)) {
        gc_page_t* page; ptrdiff_t slot;
        _object_get_page_and_slot(ptr, &page, &slot);
        page->marks[slot] |= 1;
    }
}

HIDDEN void _object_mark_as_seen2(object_t** ptrptr) {
    _object_mark_as_seen(*ptrptr);
}





EXTERN void object_allocator_init() {
    allocator_struct.initialised = true;
}

EXPORT object_t* object_mutation(object_t* ptr) {
    // Scanning not implemented yet...  Kept this in so as to not loose
    // the concept and partial implementation of "riding the wave front".
    if (_marking_in_progress && _object_is_on_heap(ptr)) {
        if (LIKELY(_object_is_on_heap(ptr))) {
            gc_page_t* page; ptrdiff_t slot;
            _object_get_page_and_slot(ptr, &page, &slot);
            if (page->marks[(gc_page_slot_t*)ptr - page->slots] != 3) {
                _object_scan(ptr);
            }
        }
    }
    return ptr;
}

EXPORT void* object_create(vtable_t* vtable) {
    assert(vtable->array_el_size == 0);
    void* object = _object_alloc(vtable->object_size);
    assert(object != NULL);
    *(char**)&((object_t*)object)->vtable = ((char*)vtable)+1;
    return object;
}

EXPORT void* array_create(vtable_t* vtable, int32_t length) {
    assert(length >= 0);
    assert(vtable->array_el_size != 0);
    void* object = _object_alloc(vtable->object_size + vtable->array_el_size*length);
    assert(object != NULL);
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


