/*
 * Minimal GC thrash test — the simplest possible reproduction of "allocate far
 * more garbage than the heap and rely on the collector to keep up".
 *
 * Single thread (run with YAFL_THREADS=1). A 200-byte object holding only a
 * char array (NO object pointers, so the GC scan has nothing to trace). Allocate
 * 1 GiB worth of them in a tight loop, keeping only the latest. With a 100 MiB
 * heap (YAFL_HEAP_SIZE=100m) the GC MUST reclaim the discarded objects or the
 * heap fills and aborts.
 *
 * Build (against the debug runtime archive):
 *   clang -I yafllib -O0 -g yafllib/tests/test_gc_thrash.c \
 *       yafllib/build/debug-unix/libyafl.a -lpthread -lm -ldl -o /tmp/gc_thrash
 * Run:
 *   YAFL_THREADS=1 YAFL_HEAP_SIZE=100m YAFL_GC_STATS=1 /tmp/gc_thrash
 */

#include "../yafl.h"
#include <stdio.h>

struct blob {
    object_t parent;        /* vtable pointer (8 bytes) */
    char     data[192];     /* → 200 bytes total, pure payload, no pointers */
};

static vtable_t blob_vt = {
    .object_size                = sizeof(struct blob),
    .array_el_size              = 0,
    .object_pointer_locations   = 0,
    .array_el_pointer_locations = 0,
    .functions_mask             = 0,
    .array_len_offset           = 0,
    .is_mutable                 = 0,
    .name                       = "blob",
    .implements_array           = VTABLE_IMPLEMENTS(0),
};

static roots_declaration_func_t prev_roots;
static void declare_roots(void(*declare)(object_t**)) { prev_roots(declare); }

static void run_loop(object_t* unused, fun_t continuation) {
    (void)unused;
    const long count = 1024L * 1024 * 1024 / (long)sizeof(struct blob);  /* 1 GiB worth */
    volatile object_t* keep = NULL;
    for (long i = 0; i < count; i++) {
        GC_SAFE_POINT();               /* per-iteration check-in, as codegen should emit on back edges */
        struct blob* b = (struct blob*)object_create(&blob_vt);
        b->data[0] = (char)i;          /* touch the payload */
        keep = (object_t*)b;           /* hold only the latest; the rest is garbage */
    }
    (void)keep;
    printf("survived: allocated %ld objects (%ld MiB total)\n",
           count, count * (long)sizeof(struct blob) / 1024 / 1024);
    fflush(stdout);
    fun_t k = continuation;
    ((void(*)(object_t*, object_t*))k.f)(k.o, INTEGER_LITERAL_1(0, 0));
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_loop);
    return 0;
}
