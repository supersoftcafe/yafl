
/*
 * Mixed-size GC churn. Allocates three size classes interleaved:
 *   - small  (fits in a bump region with hundreds of siblings)
 *   - medium (fills most of one page on its own)
 *   - large  (exceeds MAX_OBJECT_SIZE, exercises the multi-page path)
 *
 * Half the references are dropped to force the GC to reclaim, then a second
 * wave allocates over the holes. Finally every survivor is verified against
 * the pattern it was filled with — corruption from a misplaced compaction
 * or a stomp by the multi-page allocator would show up here.
 */

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>


// Mutable so the page is never compacted (which would rewrite our test
// pointers from under us). u64 elements hold no managed pointers so the GC
// does not try to follow them.
struct bytes_obj {
    object_t header;
    uint32_t length;
    uint32_t _pad;
    uint64_t data[];
};

static vtable_t bytes_vt = {
    .object_size                = offsetof(struct bytes_obj, data[0]),
    .array_el_size              = sizeof(uint64_t),
    .object_pointer_locations   = 0,
    .array_el_pointer_locations = 0,
    .array_len_offset           = offsetof(struct bytes_obj, length),
    .is_mutable                 = 1,
    .name                       = "bytes_obj",
    .implements_array           = VTABLE_IMPLEMENTS(0),
};


// Root: a managed array of object pointers. Drop a slot to ⇒ NULL to let
// the referenced bytes_obj become collectible.
struct root_obj {
    object_t  header;
    uint32_t  length;
    uint32_t  _pad;
    object_t* items[];
};

static vtable_t root_vt = {
    .object_size                = offsetof(struct root_obj, items[0]),
    .array_el_size              = sizeof(object_t*),
    .object_pointer_locations   = 0,
    .array_el_pointer_locations = maskof(object_t*, ),
    .array_len_offset           = offsetof(struct root_obj, length),
    .is_mutable                 = 1,
    .name                       = "root_obj",
    .implements_array           = VTABLE_IMPLEMENTS(0),
};


static struct bytes_obj* alloc_bytes(uint32_t len, uint64_t base) {
    struct bytes_obj* o = (struct bytes_obj*)array_create(&bytes_vt, (int32_t)len);
    for (uint32_t i = 0; i < len; ++i)
        o->data[i] = base + i;
    return o;
}

static bool verify_bytes(struct bytes_obj* o) {
    uint64_t base = o->data[0];
    for (uint32_t i = 1; i < o->length; ++i)
        if (o->data[i] != base + i)
            return false;
    return true;
}


enum {
    N_SLOTS    = 384,
    CHURN_WAVES = 16,

    SMALL_LEN  = 4,      // 32 bytes — many fit in a single bump page
    MEDIUM_LEN = 1000,   // 8000 bytes — close to MAX_OBJECT_SIZE, one per page
    LARGE_LEN  = 8000,   // 64000 bytes — exceeds MAX_OBJECT_SIZE, multi-page
};

static uint32_t size_for_index(int idx) {
    switch (idx % 3) {
        case 0:  return SMALL_LEN;
        case 1:  return MEDIUM_LEN;
        default: return LARGE_LEN;
    }
}

// Mix in the wave so the pattern written on overwrite is distinct from the
// original, and from other waves. base ≠ 0 so verify_bytes won't accidentally
// pass on a memset'd page.
static uint64_t pattern_for(int slot, int wave) {
    return ((uint64_t)slot * 0x9E3779B97F4A7C15ULL)
         ^ ((uint64_t)wave * 0xBF58476D1CE4E5B9ULL)
         | 1;
}


static void run_test(object_t* _unused, fun_t continuation) {
    (void)_unused;
    printf("=== large objects test ===\n");
    printf("  %-50s ", "mixed_sizes_survive_gc_churn");
    fflush(stdout);

    struct root_obj* root = (struct root_obj*)array_create(&root_vt, N_SLOTS);

    // Initial fill: interleaved small / medium / large across all slots.
    for (int i = 0; i < N_SLOTS; ++i) {
        GC_SAFE_POINT();
        struct bytes_obj* o = alloc_bytes(size_for_index(i), pattern_for(i, 0));
        GC_WRITE_BARRIER(root->items[i], 1);
        root->items[i] = (object_t*)o;
    }

    // Churn waves: each wave drops every other reference, then refills with a
    // fresh allocation at the same slot. Forces the GC to reclaim and the
    // multi-page allocator to land objects in churn-pattern holes.
    for (int wave = 1; wave <= CHURN_WAVES; ++wave) {
        for (int i = 0; i < N_SLOTS; i += 2) {
            GC_WRITE_BARRIER(root->items[i], 1);
            root->items[i] = NULL;
        }

        for (int i = 0; i < N_SLOTS; i += 2) {
            GC_SAFE_POINT();
            struct bytes_obj* o = alloc_bytes(size_for_index(i + wave), pattern_for(i, wave));
            GC_WRITE_BARRIER(root->items[i], 1);
            root->items[i] = (object_t*)o;
        }
    }

    // Verify every survivor. Each survivor was filled with `data[0] = base`
    // and `data[k] = base + k`; check that's still true.
    int corruptions = 0;
    int survivors = 0;
    for (int i = 0; i < N_SLOTS; ++i) {
        struct bytes_obj* o = (struct bytes_obj*)root->items[i];
        if (o == NULL) continue;
        survivors += 1;
        if (!verify_bytes(o)) corruptions += 1;
    }

    if (corruptions > 0) {
        printf("FAIL\n    %d of %d survivors had corrupted contents\n", corruptions, survivors);
        exit(1);
    }
    if (survivors == 0) {
        printf("FAIL\n    no survivors — pressure test reclaimed everything\n");
        exit(1);
    }
    printf("OK (%d survivors)\n", survivors);

    ((void(*)(object_t*, object_t*))continuation.f)(continuation.o, INTEGER_LITERAL_1(0, 0));
}


int main(void) {
    thread_start(run_test);
    return 0;
}
