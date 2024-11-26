//
// Created by mbrown on 09/03/24.
//

#include <string.h>
#include <assert.h>
#include <alloca.h>
#include <stdarg.h>
#include <threads.h>

#include "blitz.h"
#include "object.h"
#include "mmap.h"
#include "threads.h"
#include "settings.h"







enum { ALLOCATION_UNIT_SIZE_SHIFT = 16 };
enum { ALLOCATION_UNIT_SIZE = 1 << ALLOCATION_UNIT_SIZE_SHIFT };

enum { SMALLEST_ALLOCATION_SHIFT = 4 };
enum { SMALLEST_ALLOCATION = 1 << SMALLEST_ALLOCATION_SHIFT };

enum { MAX_THEORY_OBJECT_COUNT_SHIFT = ALLOCATION_UNIT_SIZE_SHIFT - SMALLEST_ALLOCATION_SHIFT };
enum { MAX_THEORY_OBJECT_COUNT = 1 << MAX_THEORY_OBJECT_COUNT_SHIFT };

enum { MAX_OBJECT_SIZE = 1 << 14 };

enum { BIT_ARRAY_SIZE = MAX_THEORY_OBJECT_COUNT / sizeof(size_t) / 8 };

struct heap_entry {
    _Alignas(SMALLEST_ALLOCATION)
    size_t p[SMALLEST_ALLOCATION / sizeof(size_t)];
};
typedef struct heap_entry heap_entry_t;

struct heap_node_bits {
    size_t seen[BIT_ARRAY_SIZE];
    size_t scanned[BIT_ARRAY_SIZE];
};

struct heap_node {
    heap_t* owner;
    heap_node_t* next;
    uint_fast32_t usage_after_sweep;    // After a sweep this should reflect the actual number of bytes allocated.
    char compaction_candidate;

    struct heap_node_bits bits;
    struct heap_entry start[0];
};

enum { MAX_OBJECT_COUNT = (ALLOCATION_UNIT_SIZE - sizeof(struct heap_node)) / SMALLEST_ALLOCATION };


static char* final_heap_node_ptr_;
static char* next_heap_node_ptr_;
static char* first_heap_node_ptr_;
static struct heap_node* global_free_heap_nodes_;
static mtx_t global_free_heap_nodes_lock_;

thread_local int free_heap_nodes_count_;
thread_local heap_node_t* free_heap_nodes_;
thread_local heap_t* local_heap_;



void object_init() {
    size_t size = 1<<28;
    first_heap_node_ptr_ = mmap_alloc_aligned(size, ALLOCATION_UNIT_SIZE_SHIFT);
    final_heap_node_ptr_ = first_heap_node_ptr_ + size;
    next_heap_node_ptr_ = first_heap_node_ptr_;
}

func_t object_vlookup(object_t* object, uintptr_t function_id) {
    vtable_t* vtable = object->vtable;
    uintptr_t offset = function_id & vtable->functions_mask; // Mask *MUST* result in an aligned byte offset
    vtable_entry_t* entry = (vtable_entry_t*)((char*)(vtable->functions-1) + offset);
    while ((++entry)->function_id != function_id)
        assert(entry->function_id != 0);
    return entry->function;
}

static inline
uint32_t *ref_array_length(object_t *object) {
    return &((uint32_t*)object)[object->vtable->array_len_index];
}



static inline
heap_node_t *object_create_new_page(heap_t* heap) {
    heap_node_t* new_node;

    if ((new_node = free_heap_nodes_) != NULL) {
        free_heap_nodes_ = new_node->next;
        free_heap_nodes_count_ -= 1;
    } else {
        mtx_lock(&global_free_heap_nodes_lock_);
        new_node = global_free_heap_nodes_;
        if (new_node != NULL) {
            global_free_heap_nodes_ = new_node->next;
        } else if (next_heap_node_ptr_ < final_heap_node_ptr_) {
            new_node = (struct heap_node*)next_heap_node_ptr_;
            next_heap_node_ptr_ += ALLOCATION_UNIT_SIZE;
        } else {
            ERROR("out of memory");
        }
        mtx_unlock(&global_free_heap_nodes_lock_);
    }

    new_node->compaction_candidate = 0;
    new_node->next = heap->current_head;
    new_node->owner = heap;

    heap->current_head = new_node;
    heap->node_count += 1;

    return new_node;
}

static inline
void object_release_old_page(heap_node_t* node) {
    if (free_heap_nodes_count_ < 256) {
        node->next = free_heap_nodes_;
        free_heap_nodes_ = node;
    } else {
        mtx_lock(&global_free_heap_nodes_lock_);
        node->next = global_free_heap_nodes_;
        global_free_heap_nodes_ = node;
        mtx_unlock(&global_free_heap_nodes_lock_);
    }
}

static __attribute__((noinline))
object_t* object_create_internal2(heap_t* heap, size_t size) {
    size = (size + SMALLEST_ALLOCATION - 1) & ~(SMALLEST_ALLOCATION - 1);
    assert(size > 0 && size <= MAX_OBJECT_SIZE);

    uintptr_t ptr = heap->next - size;
    if (unlikely(ptr < heap->base)) {
        heap_node_t *node = object_create_new_page(heap);
        heap->base = (uintptr_t)node->start;
        ptr = ALLOCATION_UNIT_SIZE + (uintptr_t)node - size;
    }

    heap->next = ptr;
    return (object_t*)ptr;
}

object_t* object_create_internal(size_t size) {
    return object_create_internal2(local_heap_, size);
}

__attribute__((noinline))
void object_heap_create(heap_t* heap) {
    heap->current_head = NULL;
    heap->node_count = 0;
    heap->base = 0x7fffffff;
    heap->next = 0x7fffffff;
}

__attribute__((noinline))
void object_heap_select(heap_t* heap) {
    local_heap_ = heap;
}

__attribute__((noinline))
void object_heap_destroy(heap_t* heap) {
    heap->node_count = 0;
    while (heap->current_head != NULL) {
        heap_node_t *node = heap->current_head;
        heap->current_head = node->next;
        object_release_old_page(node);
    }
}

__attribute__((noinline))
void object_heap_append(heap_t* heap, heap_t* sub_heap) {
    heap_node_t *sub_head = sub_heap->current_head;
    if (sub_head == NULL) return; // There's nothing to do, and later code will SIGFAULT if we don't return

    heap_node_t *sub_tail = sub_head;
    while (sub_tail->next != NULL) {
        sub_tail->owner = heap;
        sub_tail = sub_tail->next;
    }
    sub_tail->owner = heap;
    sub_tail->next = heap->current_head;

    heap->current_head = sub_head;
    heap->node_count += sub_heap->node_count;

    sub_heap->current_head = NULL;
    sub_heap->node_count = 0;
}


static inline
heap_node_t* get_heap_node(object_t* object) {
    return (heap_node_t *) ((~(ALLOCATION_UNIT_SIZE - 1)) & ((intptr_t)object));
}

static inline
ptrdiff_t get_object_index(object_t* object, heap_node_t* node) {
    return ((heap_entry_t*) object) - node->start;
}

static inline
int is_valid_pointer(object_t* object) {
    char* c = (char*)object;
    return c >= first_heap_node_ptr_ && c < final_heap_node_ptr_ && ((uintptr_t)c & (sizeof(uintptr_t)*2-1)) == 0;
}

static inline
void set_object_bit(object_t* object, heap_node_t* node, size_t* bits) {
    ptrdiff_t index = get_object_index(object, node);
    size_t entry = index / total_bits(size_t);
    size_t shift = index % total_bits(size_t);
    size_t bit = ((size_t)1) << shift;
    bits[entry] |= bit;
}

static inline
void mark_seen(heap_t* heap, object_t **object_ptr) {
    object_t *object = *object_ptr;
    if (is_valid_pointer(object)) {
        heap_node_t *node = get_heap_node(object);
        if (node->owner == heap)
            set_object_bit(object, node, node->bits.seen);
    }
}

static inline
void mark_scanned(object_t* object) {
    heap_node_t *node = get_heap_node(object);
    set_object_bit(object, node, node->bits.scanned);
}

static inline
void visit_each_ pointer2(heap_t* heap, void** base_pointer, uint32_t layout, void(*visitor)(void*,void*)) {
    for (int index = 0; index < 32; ++index) {
        if ((layout & (1 << index)) != 0)
            visitor(heap, &base_pointer[index]);
    }
}

static inline
void visit_each_pointer(heap_t *heap, object_t *object, void(*visitor)(void*,void*)) {
    vtable_t* vtable = object->vtable;
    visit_each_pointer2(heap, ((void**)object)+1, vtable->object_pointer_locations, visitor);

    if (vtable->array_el_pointer_locations != 0) {
        uint16_t el_size = vtable->array_el_size;
        uint32_t array_length = *ref_array_length(object);
        char *base_pointer = ((char*)object) + vtable->object_size;
        for (uint32_t index = 0; index < array_length; ++index, base_pointer += el_size) {
            visit_each_pointer2(heap, (void **) base_pointer, vtable->array_el_pointer_locations, visitor);
        }
    }
}

static inline
void fix_pointer(__attribute__((unused)) heap_t *heap, object_t **object_ptr) {
    object_t *old_object = *object_ptr;
    if (is_valid_pointer(old_object)) {
        heap_node_t *node = get_heap_node(old_object);
        if (node->owner == heap && node->compaction_candidate) {
            object_t *new_ptr = (object_t *) (old_object->vtable);
            *object_ptr = new_ptr;
        }
    }
}

static inline
void fix_pointers(heap_t *heap, object_t* object) {
    visit_each_pointer(heap, object, (void(*)(void*,void*))fix_pointer);
}


static inline
size_t size_of_object(object_t *object) {
    vtable_t *vtable = object->vtable;
    size_t size = vtable->object_size;
    if (vtable->array_el_size != 0)
        size += vtable->array_el_size * (size_t)*ref_array_length(object);
    return size;
}


static inline
void scan_object(heap_t* heap, object_t* object) {
    mark_scanned(object);
    visit_each_pointer(heap, object, (void(*)(void*,void*))mark_seen);
}


static __attribute__((noinline))
void mark_sweep(heap_t *heap) {
    for (size_t loop_flags = 1; loop_flags; ) {
        loop_flags = 0;
        for (heap_node_t *node = heap->current_head; node; node = node->next) {

            for (size_t index = 0; index < BIT_ARRAY_SIZE; ++index) {
                for (size_t to_scan; (to_scan = node->bits.seen[index] & ~node->bits.scanned[index]) != 0;) {
                    if (to_scan) {
                        loop_flags |= to_scan;
                        size_t shift = index_of_lowest_bit(to_scan);
                        size_t entry = index * total_bits(size_t) + shift;

                        object_t *object = (object_t *) &node->start[entry];
                        node->usage_after_sweep += size_of_object(object);
                        scan_object(heap, object);
                    }
                }
            }

            node->compaction_candidate = node->usage_after_sweep < ALLOCATION_UNIT_SIZE/2;
        }
    }
}


static __attribute__((noinline))
void copy_to_new_heap(heap_t *heap, heap_t *new_heap) {
    for (heap_node_t *node = heap->current_head; node; node = node->next) {
        if (node->compaction_candidate) {
            for (size_t index = 0; index < BIT_ARRAY_SIZE; ++index) {

                size_t seen = node->bits.seen[index];
                while (seen != 0) {
                    size_t shift = index_of_lowest_bit(seen);
                    size_t entry = index * total_bits(size_t) + shift;
                    seen ^= ((size_t) 1) << shift;

                    // Allocate and copy to new space
                    object_t* old_object = (object_t*) &node->start[entry];
                    size_t size = size_of_object(old_object);
                    object_t* new_object = object_create_internal2(new_heap, size);
                    memcpy(new_object, old_object, size);

                    // Write redirect pointer into old object for later lookup
                    ((object_t*)old_object)->vtable = (vtable_t *) new_object;
                }
            }
        }
    }
}


static __attribute__((noinline))
void fix_object_references(heap_t *old_heap) {
    for (heap_node_t *node = old_heap->current_head; node; node = node->next) {
        if (node->compaction_candidate) {
            for (size_t index = 0; index < BIT_ARRAY_SIZE; ++index) {

                size_t seen = node->bits.seen[index];
                while (seen != 0) {
                    size_t shift = index_of_lowest_bit(seen);
                    size_t entry = index * total_bits(size_t) + shift;
                    seen ^= ((size_t) 1) << shift;

                    object_t *old_object = (object_t *) &node->start[entry];
                    object_t *new_object = (object_t *) old_object->vtable;
                    fix_pointers(old_heap, new_object);
                }
            }
        }
    }
}


static inline
void walk_roots(heap_t *heap, va_list ap, void(*visitor)(heap_t*,object_t**)) {
    for (object_t** pointer; (pointer = va_arg(ap, object_t**)) != NULL; ) {
        visitor(heap, pointer);
    };
}

static __attribute__((noinline))
void mark_each_root_object_as_seen(heap_t* heap, va_list ap) {
    walk_roots(heap, ap, mark_seen);
}


static __attribute__((noinline))
void fixup_the_roots(heap_t *old_heap, va_list ap) {
    walk_roots(old_heap, ap, fix_pointer);
}


static __attribute__((noinline))
void clear_all_seen_scanned_bits(heap_t *heap) {
    for (heap_node_t *node = heap->current_head; node; node = node->next) {
        node->usage_after_sweep = 0;
        node->compaction_candidate = 0;
        memset(&node->bits, 0, sizeof(node->bits));
    }
}


static __attribute__((noinline))
void destroy_the_old_heap(heap_t *heap, heap_t *new_heap) {
    for (heap_node_t **node_ptr = &heap->current_head; *node_ptr; ) {
        heap_node_t *node = *node_ptr;
        if (node->compaction_candidate == 0) {
            // Unlink it from the old heap
            *node_ptr = node->next;
            // Link into the new heap
            node->next = new_heap->current_head;
            new_heap->current_head = node;
        } else {
            node_ptr = &node->next;
        }
    }
    object_heap_destroy(heap);
}


__attribute__((noinline))
void object_heap_compact(heap_t* heap, ...) {
    va_list ap;

    // Early return for heaps that can't be compacted
    if (heap->current_head == NULL || heap->current_head->next == NULL)
        return;

    // 1. Clear all seen/scanned bits
    clear_all_seen_scanned_bits(heap);

    // 2. Mark each root object as seen
    va_start(ap, heap);
    mark_each_root_object_as_seen(heap, ap);
    va_end(ap);

    // 3. Walk all heap objects, and scan for seen but not scanned entries
    //    For each one, scan it and mark referenced objects as seen
    mark_sweep(heap);

    // 4. Create a new heap
    heap_t new_heap;
    object_heap_create(&new_heap);

    // 5. Walk all heap objects, and copy to the new heap
    //    Corrupt the 'vtable' pointer by pointing it to the new heap object
    copy_to_new_heap(heap, &new_heap);

    // 6. Walk all heap objects, follow 'vtable' pointer to new location, fix-up all references
    //    by following the current stale references and taking the 'vtable' pointer that is now
    //    actually the new location of the object.
    fix_object_references(heap);

    // 7. Fix up the 'roots' list by overwriting with the new location of each object
    va_start(ap, heap);
    fixup_the_roots(heap, ap);
    va_end(ap);

    // 8. Destroy the old heap, but retain nodes that aren't compaction candidates
    destroy_the_old_heap(heap, &new_heap);

    // 9. Change owner to be correct
    for (heap_node_t *node = new_heap.current_head; node; node = node->next)
        node->owner = heap;

    *heap = new_heap;
}
