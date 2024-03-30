//
// Created by mbrown on 09/03/24.
//

#include <string.h>
#include <assert.h>

#include "blitz.h"
#include "object.h"
#include "mmap.h"
#include "threads.h"
#include "settings.h"


thread_local struct heap_node* free_list;
static size_t RECYCLE_COUNT = 0;

enum { ALLOCATION_UNIT_SIZE_SHIFT = 16 };
enum { ALLOCATION_UNIT_SIZE = 1 << ALLOCATION_UNIT_SIZE_SHIFT };

enum { SMALLEST_ALLOCATION_SHIFT = 4 };
enum { SMALLEST_ALLOCATION = 1 << SMALLEST_ALLOCATION_SHIFT };

enum { LARGEST_ALLOCATION_SHIFT = 14 };
enum { LARGEST_ALLOCATION = 1 << LARGEST_ALLOCATION_SHIFT };

enum { MAX_THEORY_OBJECT_COUNT_SHIFT = ALLOCATION_UNIT_SIZE_SHIFT - SMALLEST_ALLOCATION_SHIFT };
enum { MAX_THEORY_OBJECT_COUNT = 1 << MAX_THEORY_OBJECT_COUNT_SHIFT };

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
    _Alignas(SMALLEST_ALLOCATION)
    struct heap_node_bits bits;
    size_t recycle_count;
    heap_node_t* next;
    heap_t* owner;
    uint32_t next_object_index; // Subtract object size (as count of min unit) to get next index

    uint32_t usage_after_sweep;     // After a sweep this should reflect the actual number of bytes allocated.
    uint8_t compaction_candidate;   // During compaction is this node a candidate. If not, don't corrupt objects and don't copy.

    struct heap_entry start[0];
};

enum { MAX_OBJECT_COUNT = (ALLOCATION_UNIT_SIZE - sizeof(struct heap_node)) / SMALLEST_ALLOCATION };



void object_init() {
    RECYCLE_COUNT = 10;
}


static inline
uint32_t *ref_array_length(object_t *object) {
    return (uint32_t*)&((char*)object)[object->vtable->array_len_offset];
}


func_t object_function_lookup(object_t* object, uintptr_t function_id) {
    vtable_t* vtable = object->vtable;
    uintptr_t index = function_id & vtable->functions_mask;
    vtable_entry_t * entry = (vtable_entry_t*)(((char*)(vtable->functions-1)) + index);
    while ((++entry)->function_id != function_id)
        assert(entry->function_id != 0);
    return entry->function;
}


__attribute__((noinline))
static void object_create_new_page(heap_t* heap) {
    // Allocate a new page
    heap_node_t* new_node = free_list;
    if (new_node != NULL) {
        free_list = new_node->next;
    } else {
        new_node = mmap_alloc(ALLOCATION_UNIT_SIZE, ALLOCATION_UNIT_SIZE_SHIFT);
    }

    new_node->next_object_index = MAX_OBJECT_COUNT;
    new_node->next = heap->current_head;
    new_node->owner = heap;
    heap->current_head = new_node;
    heap->node_count += 1;

    assert(new_node->recycle_count == 0);
    assert(new_node->compaction_candidate == 0);
}

__attribute__((noinline))
static void object_release_old_page(heap_node_t* node) {
    if (++node->recycle_count >= RECYCLE_COUNT) {
        mmap_release(ALLOCATION_UNIT_SIZE, node);
    } else {
        // Only zero the used portion, as nothing else has changed from original zero.
        heap_entry_t *start = &node->start[node->next_object_index];
        memset(start, 0, sizeof(heap_entry_t) * (MAX_OBJECT_COUNT - node->next_object_index));
        node->compaction_candidate = 0;
        node->recycle_count = 0;

        // Add to the thread local free list
        node->next = free_list;
        free_list = node;
    }
}

object_t* object_create_internal(heap_t* heap, vtable_t* vtable, uint64_t size) {
    assert(size > 0 && size <= LARGEST_ALLOCATION);

    // Convert to count of smallest allocation units
    size = (size + SMALLEST_ALLOCATION - 1) / SMALLEST_ALLOCATION;

    if (heap->current_head == NULL || size > heap->current_head->next_object_index)
        object_create_new_page(heap);
    heap_node_t *node = heap->current_head;

    assert(node != NULL && size <= node->next_object_index);

    heap->object_count += 1;
    heap->used_space += size * SMALLEST_ALLOCATION;
    node->next_object_index -= (uint32_t)size;

    object_t* object = (object_t*)&node->start[node->next_object_index];
    object->vtable = vtable;

    return object;
}

object_t* object_create_array(heap_t* heap, vtable_t* vtable, uint32_t length) {
    assert(vtable->object_layout != NULL);
    assert(vtable->array_layout != NULL);
    assert(vtable->array_len_offset >= sizeof(vtable_t*));

    uint64_t size = vtable->array_layout->size * (uint64_t)length + vtable->object_layout->size;
    object_t* object = object_create_internal(heap, vtable, size);
    *ref_array_length(object) = length;

    return object;
}

object_t* object_create(heap_t* heap, vtable_t* vtable) {
    assert(vtable->object_layout != NULL);
    assert(vtable->array_layout == NULL);
    assert(vtable->array_len_offset == 0);

    uint64_t size = vtable->object_layout->size;
    object_t* object = object_create_internal(heap, vtable, size);

    return object;
}



__attribute__((noinline))
void object_heap_create(heap_t* heap) {
    heap->current_head = NULL;
    heap->object_count = 0;
    heap->used_space = 0;
    heap->node_count = 0;
}

__attribute__((noinline))
void object_heap_destroy(heap_t* heap) {
    heap->object_count = 0;
    heap->used_space = 0;
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
    heap->object_count += sub_heap->object_count;
    heap->node_count += sub_heap->node_count;
    heap->used_space += sub_heap->used_space;

    sub_heap->current_head = NULL;
    sub_heap->object_count = 0;
    sub_heap->used_space = 0;
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
    if (object != NULL) {
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
void visit_each_pointer2(heap_t* heap, char* base_pointer, layout_t *layout, void(*visitor)(void*,void*)) {
    for (uint32_t index = 0; index < layout->pointer_count; ++index) {
        uint32_t offset = layout->pointer_offsets[index];
        visitor(heap, base_pointer + offset);
    }
}

static inline
void visit_each_pointer(heap_t* heap, object_t* object, void(*visitor)(void*,void*)) {
    layout_t *object_layout = object->vtable->object_layout;
    layout_t * array_layout = object->vtable->array_layout;

    visit_each_pointer2(heap, (char*)object, object_layout, visitor);

    if (array_layout != NULL && array_layout->pointer_count > 0) {
        char* base_pointer = ((char*)object) + object_layout->size;
        uint32_t array_length = *ref_array_length(object);
        for (uint32_t index = 0; index < array_length; ++index, base_pointer += array_layout->size)
            visit_each_pointer2(heap, base_pointer, array_layout, visitor);
    }
}

static inline
void scan_object(heap_t* heap, object_t* object) {
    mark_scanned(object);
    visit_each_pointer(heap, object, (void(*)(void*,void*))mark_seen);
}

static inline
void fix_pointer(__attribute__((unused)) heap_t *heap, object_t **object_ptr) {
    object_t* old_object = *object_ptr;
    if (old_object != NULL) {
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
    size_t size = vtable->object_layout->size;
    if (vtable->array_layout != NULL)
        size += vtable->array_layout->size * *ref_array_length(object);
    return size;
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

                    object_t *old_object = (object_t *) &node->start[entry];
                    size_t size = size_of_object(old_object);
                    object_t *new_object = object_create_internal(new_heap, old_object->vtable, size);
                    memcpy(new_object, old_object, size);

                    // Write redirect pointer into old object for later lookup
                    old_object->vtable = (vtable_t *) new_object;
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

__attribute__((noinline))
void object_heap_compact(heap_t *heap, int root_count, object_t **roots) {
    // Early return for heaps that can't be compacted
//    if (heap->current_head == NULL || heap->current_head->next == NULL)
//        return;

    // 1. Clear all seen/scanned bits
    for (heap_node_t *node = heap->current_head; node; node = node->next) {
        node->usage_after_sweep = 0;
        node->compaction_candidate = 0;
        memset(&node->bits, 0, sizeof(node->bits));
    }

    // 2. Mark each root object as seen
    for (int index = 0; index < root_count; ++index)
        mark_seen(heap, &roots[index]);

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
    for (int index = root_count; --index >= 0; )
        fix_pointer(heap, &roots[index]);

    // 8. Destroy the old heap, but retain nodes that aren't compaction candidates
    for (heap_node_t **node_ptr = &heap->current_head; *node_ptr; ) {
        heap_node_t *node = *node_ptr;
        if (node->compaction_candidate == 0) {
            // Unlink it from the old heap
            *node_ptr = node->next;
            // Link into the new heap
            node->next = new_heap.current_head;
            new_heap.current_head = node;
        } else {
            node_ptr = &node->next;
        }
    }
    object_heap_destroy(heap);

    // 9. Change owner to be correct
    for (heap_node_t *node = new_heap.current_head; node; node = node->next)
        node->owner = heap;

    *heap = new_heap;
}
