// The scan rate's definition (gc_scan_rate_for, object.c): the base rate
// while the heap is at most half full; past that, double for every halving of
// the free heap; capped at 64x base. Pure arithmetic, no collector needed.

#include "../yafl.h"
#include <stdio.h>
#include <stdlib.h>

extern unsigned gc_scan_rate_for(size_t used, size_t total, unsigned base);

static int failures = 0;
static void expect(size_t used, size_t total, unsigned base, unsigned want) {
    unsigned got = gc_scan_rate_for(used, total, base);
    if (got != want) {
        fprintf(stderr, "test_gc_scan_rate: FAIL rate(used=%zu, total=%zu, base=%u) = %u, want %u\n",
                used, total, base, got, want);
        ++failures;
    }
}

int main(void) {
    const size_t T = 65536;   // a 1 GB heap of 16 KB pages
    const unsigned B = 6;     // GC_PACE_SCAN_PAGES

    // At most half full: the base rate.
    expect(0, T, B, B);
    expect(T / 4, T, B, B);
    expect(T / 2, T, B, B);

    // Each halving of the free heap doubles it.
    expect(T - T / 4,  T, B, 2 * B);    // a quarter free
    expect(T - T / 8,  T, B, 4 * B);    // an eighth
    expect(T - T / 16, T, B, 8 * B);
    expect(T - T / 32, T, B, 16 * B);
    expect(T - T / 64, T, B, 32 * B);

    // Capped at 64x: at 1/128 free and beyond, full or over-full.
    expect(T - T / 128, T, B, 64 * B);
    expect(T - 1, T, B, 64 * B);
    expect(T, T, B, 64 * B);
    expect(T + 10, T, B, 64 * B);

    // Between the doublings it is continuous, rounded up: 3/8 free -> 4/3 x.
    expect(T - 3 * T / 8, T, B, (unsigned)((B * (T / 2) + 3 * T / 8 - 1) / (3 * T / 8)));

    // Monotonic in usage, and never below base, over the whole heap.
    unsigned prev = 0;
    for (size_t used = 0; used <= T; used += 7) {
        unsigned r = gc_scan_rate_for(used, T, B);
        if (r < prev || r < B) {
            fprintf(stderr, "test_gc_scan_rate: FAIL not monotonic at used=%zu (%u after %u)\n", used, r, prev);
            ++failures;
            break;
        }
        prev = r;
    }

    // Easing off: the same usage gives the same rate on the way down.
    expect(T - T / 8, T, B, 4 * B);
    expect(T / 2, T, B, B);

    if (failures) return 1;
    printf("test_gc_scan_rate: OK\n");
    return 0;
}
