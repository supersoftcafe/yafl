// The DWELL between cycles (object.c, the pacing comment): once a cycle ends,
// the next opens only after YAFL_GC_IDLE_PAGES pages have been allocated.
//
// One thread allocates unrooted page-sized objects, so every allocation is
// one page refill and one paced collector step, and the collector runs only
// inside those steps. The test watches the stage after each allocation and
// counts the pages from each cycle's end (IDLE) to the next cycle's start
// (anything else). Every gap must cover the dwell. Without one, the next
// allocation opens the next cycle at once: a gap of one page.
//
// Run with YAFL_THREADS=1, so no other worker steps the collector.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern int gc_debug_stage(void);

// Must match enum gc_stage in object.c.
enum { ST_IDLE = 1 };
enum { IDLE_PAGES = 64, CYCLES = 4 };

// More than half a page's slots, so no two share a page.
struct big { object_t parent; char pad[MAX_OBJECT_SIZE * 3 / 4]; };
static vtable_t big_vt = {
    .object_size = sizeof(struct big), .array_el_size = 0,
    .object_pointer_locations = 0, .array_el_pointer_locations = 0,
    .functions_mask = 0, .array_len_offset = 0,
    .is_mutable = 0, .name = "dwell_big", .implements_array = VTABLE_IMPLEMENTS(0),
};

static fun_t _exit_cont;

static void fail(const char* what, long value) {
    fprintf(stderr, "test_gc_dwell: FAIL %s (%ld)\n", what, value);
    fflush(stderr);
    abort();
}

static void _entrypoint(object_t* self, fun_t cont) {
    (void)self; _exit_cont = cont;
    while (gc_debug_stage() == 0) usleep(1000);   // wait for the collector

    long pages = 0, idle_at = -1;
    int gaps = 0, prev = gc_debug_stage();
    while (gaps < CYCLES) {
        if (pages > 1000000) fail("too few cycles in a million pages", gaps);
        (void)object_create(&big_vt);
        pages += 1;
        int now = gc_debug_stage();
        if (now == ST_IDLE && prev != ST_IDLE) {
            idle_at = pages;                       // a cycle ended
        } else if (now != ST_IDLE && prev == ST_IDLE && idle_at >= 0) {
            long gap = pages - idle_at;            // the next one opened
            if (gap < IDLE_PAGES - 2) fail("a cycle opened inside the dwell: gap", gap);
            gaps += 1;
        }
        prev = now;
    }
    printf("test_gc_dwell: OK\n");
    fflush(stdout);
    ((void(*)(object_t*,object_t*))_exit_cont.f)(_exit_cont.o, integer_from_int32(0));
}

int main(void) {
    // Small enough to run quickly; far below half the heap, where the dwell
    // gives way. Set before any allocation; the environment may override.
    setenv("YAFL_HEAP_SIZE", "256m", 0);
    setenv("YAFL_GC_IDLE_PAGES", "64", 0);
    thread_start(_entrypoint);
    return 0;
}
