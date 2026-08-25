// The heap census (heapprof.c): per-thread accumulation, cycle merge, and
// the massif stream.
//
// What these tests pin down:
//
//   * disabled (no YAFL_HEAPPROF): every entry point is a no-op;
//   * census sums bytes per vtable across calls and threads-worth of
//     tables, merged and RESET by cycle_end;
//   * the massif file parses: header, one snapshot per cycle_end, totals
//     lines, and a detailed tree whose per-type children carry the exact
//     censused bytes under the exact vtable names;
//   * mem_heap_extra_B = reserved - in_use, clamped at zero.
#include "../yafl.h"
#include "../heapprof.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CHECK(cond, msg) do { if (!(cond)) { printf("FAIL: %s\n", msg); exit(1); } } while (0)

#define OUT_PATH "test_heapprof.massif"

static vtable_t vt_a, vt_b;

static char *slurp(const char *path) {
    FILE *f = fopen(path, "r");
    CHECK(f != NULL, "massif file exists");
    static char buf[65536];
    size_t n = fread(buf, 1, sizeof buf - 1, f);
    buf[n] = '\0';
    fclose(f);
    return buf;
}

int main(void) {
    vt_a.name = "test::Alpha";
    vt_b.name = "test::Beta";

    // Disabled: everything is a no-op and crashes nothing.
    yafl_heapprof_census((const struct vtable *)&vt_a, 64);
    yafl_heapprof_cycle_end(0, 0);
    yafl_heapprof_dump();

    setenv("YAFL_HEAPPROF", OUT_PATH, 1);
    unlink(OUT_PATH);
    yafl_heapprof_init();
    CHECK(yafl_heapprof_enabled, "enabled after init with env set");

    yafl_heapprof_thread_init();
    yafl_heapprof_census((const struct vtable *)&vt_a, 100);
    yafl_heapprof_census((const struct vtable *)&vt_b, 40);
    yafl_heapprof_census((const struct vtable *)&vt_a, 28);
    yafl_heapprof_cycle_end(4096, 8192);

    // Second cycle: the tables were reset by the merge.
    yafl_heapprof_census((const struct vtable *)&vt_b, 8);
    yafl_heapprof_cycle_end(10000, 4096);   // reserved < in_use: extra clamps to 0

    yafl_heapprof_dump();

    char *text = slurp(OUT_PATH);
    CHECK(strstr(text, "time_unit: ms") != NULL, "header present");
    CHECK(strstr(text, "snapshot=0") != NULL, "first snapshot present");
    CHECK(strstr(text, "snapshot=1") != NULL, "second snapshot present");
    CHECK(strstr(text, "mem_heap_B=4096") != NULL, "first in-use total");
    CHECK(strstr(text, "mem_heap_extra_B=4096") != NULL, "extra = reserved - in_use");
    CHECK(strstr(text, "mem_heap_B=10000") != NULL, "second in-use total");
    CHECK(strstr(text, "mem_heap_extra_B=0\n") != NULL, "negative extra clamps to 0");
    CHECK(strstr(text, "n0: 128 0x0: test::Alpha") != NULL, "Alpha bytes summed (100+28)");
    CHECK(strstr(text, "n0: 40 0x0: test::Beta") != NULL, "Beta bytes in first cycle");
    CHECK(strstr(text, "n0: 8 0x0: test::Beta") != NULL, "tables reset between cycles");
    // Alpha sorts before Beta in cycle 1 (descending bytes).
    CHECK(strstr(text, "test::Alpha") < strstr(text, "test::Beta"),
          "rows sorted by bytes descending");

    unlink(OUT_PATH);
    printf("OK\n");
    return 0;
}
