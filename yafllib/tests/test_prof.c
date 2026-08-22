// The sampling profiler (prof.c): exact counters, shadow-stack balance, CPU
// sampling, and the two output files.
//
// What these tests pin down:
//
//   * enter/leave keep EXACT per-function counts — the counters half of the
//     profiler's contract is deterministic and asserted to the call;
//   * the shadow stack stays balanced past its cap (deep "recursion" is
//     counted, not stored, and sp comes back to where it started);
//   * per-thread CPU-time sampling works with NO safe points: a pure spin
//     inside an entered frame accumulates samples, asserted with a wide
//     margin (the clock is thread CPU time, so machine load cannot fail it);
//   * the callgrind and folded files exist, parse, and carry both the exact
//     counts and the sampled time;
//   * before yafl_prof_init runs, every entry point is a no-op.
#include "../yafl.h"
#include "../prof.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define CHECK(cond, msg) do { if (!(cond)) { printf("FAIL: %s\n", msg); exit(1); } } while (0)

#define OUT_PATH "test_prof.callgrind"

enum { FN_ALPHA = 0, FN_BETA = 1, FN_BURN = 2, FN_COUNT = 3 };
static const yafl_prof_fn_t TEST_FNS[FN_COUNT] = {
    { "test::alpha", "test_prof.yafl", 10 },
    { "test::beta",  "test_prof.yafl", 20 },
    { "test::burn",  "test_prof.yafl", 30 },
};

// Burn the given amount of THIS THREAD's CPU time. The condition uses
// CLOCK_THREAD_CPUTIME_ID — the same clock the sampler ticks on — so the
// expected sample count is load-independent by construction.
static uint64_t burn_thread_cpu_ns(uint64_t ns) {
    struct timespec t0, t;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t0);
    uint64_t spin = 0;
    for (;;) {
        for (int i = 0; i < 10000; i++)
            spin += (uint64_t)i * 2654435761u;
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
        uint64_t spent = (uint64_t)((t.tv_sec - t0.tv_sec) * 1000000000LL
                                  + (t.tv_nsec - t0.tv_nsec));
        if (spent >= ns)
            return spin;   // returned so the loop cannot be optimised away
    }
}

// Read a whole (small) file into a malloc'd NUL-terminated buffer.
static char* slurp(const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char* buf = malloc((size_t)n + 1);
    size_t got = fread(buf, 1, (size_t)n, f);
    buf[got] = '\0';
    fclose(f);
    return buf;
}

// Find "fn=<name>\n<line> <ns> <calls>\n" and return the two event values.
static bool callgrind_row(const char* text, const char* name,
                          unsigned long long* ns, unsigned long long* calls) {
    char key[128];
    snprintf(key, sizeof key, "fn=%s\n", name);
    const char* p = strstr(text, key);
    if (!p) return false;
    int line;
    return sscanf(p + strlen(key), "%d %llu %llu", &line, ns, calls) == 3;
}

static void run_tests(object_t* _unused, fun_t continuation) {
    (void)_unused; (void)continuation;
    int passed = 0;

    // --- exact counters ------------------------------------------------------
    {
        for (int i = 0; i < 1000; i++) {
            yafl_prof_enter(FN_ALPHA);
            if (i < 7) {
                yafl_prof_enter(FN_BETA);
                yafl_prof_leave();
            }
            yafl_prof_leave();
        }
        CHECK(yafl_prof_tl.counters != NULL, "worker 0 was not registered");
        CHECK(yafl_prof_tl.counters[FN_ALPHA] == 1000, "alpha count is not exact");
        CHECK(yafl_prof_tl.counters[FN_BETA] == 7, "beta count is not exact");
        printf("  prof_counters_are_exact                      OK\n"); passed++;
    }

    // --- shadow-stack balance past the cap -----------------------------------
    {
        int32_t sp0 = atomic_load(&yafl_prof_tl.sp);
        uint64_t before = yafl_prof_tl.counters[FN_BETA];
        for (int i = 0; i < 5000; i++)
            yafl_prof_enter(FN_BETA);           // deeper than the 4096-entry cap
        for (int i = 0; i < 5000; i++)
            yafl_prof_leave();
        CHECK(atomic_load(&yafl_prof_tl.sp) == sp0, "shadow stack unbalanced past cap");
        CHECK(yafl_prof_tl.counters[FN_BETA] == before + 5000,
              "counters lost calls past the shadow-stack cap");
        printf("  prof_stack_balances_past_cap                 OK\n"); passed++;
    }

    // --- sampling: pure spin, no safe points, no allocation ------------------
    {
        yafl_prof_enter(FN_BURN);
        uint64_t sink = burn_thread_cpu_ns(200 * 1000 * 1000);   // 200 ms CPU
        yafl_prof_leave();
        CHECK(sink != 42, "impossible");   // keep the burn observable
        printf("  prof_burned_cpu_inside_a_frame               OK\n"); passed++;
    }

    // --- dump + parse both files ---------------------------------------------
    {
        yafl_prof_dump();
        char* cg = slurp(OUT_PATH);
        char* fd = slurp(OUT_PATH ".folded");
        CHECK(cg != NULL, "callgrind file missing");
        CHECK(fd != NULL, "folded file missing");
        CHECK(strstr(cg, "events: Ns Calls") != NULL, "events line missing");
        CHECK(strstr(cg, "summary: ") != NULL, "summary line missing");

        unsigned long long ns, calls;
        CHECK(callgrind_row(cg, "test::alpha", &ns, &calls), "alpha row missing");
        CHECK(calls == 1000, "alpha calls wrong in callgrind output");
        CHECK(callgrind_row(cg, "test::beta", &ns, &calls), "beta row missing");
        CHECK(calls == 5007, "beta calls wrong in callgrind output");
        CHECK(callgrind_row(cg, "test::burn", &ns, &calls), "burn row missing");
        CHECK(calls == 1, "burn calls wrong in callgrind output");
        // 200 ms of thread CPU at the default 997 Hz is ~199 samples. Demand
        // only 20 ms worth — a 10x margin, immune to machine load because the
        // sampling clock is the thread's own CPU time.
        CHECK(ns >= 20 * 1000 * 1000, "burn self time implausibly low");

        // The folded file must attribute those samples to the burn frame.
        const char* row = strstr(fd, "test::burn ");
        CHECK(row != NULL, "burn stack missing from folded output");
        CHECK(strtoull(row + strlen("test::burn "), NULL, 10) >= 20,
              "burn folded weight implausibly low");

        free(cg);
        free(fd);
        printf("  prof_dump_writes_parseable_output            OK\n"); passed++;
    }

    unlink(OUT_PATH);
    unlink(OUT_PATH ".folded");
    printf("prof: %d passed, 0 failed\n", passed);
    exit(0);
}

int main(void) {
    // Before init, every entry point must be a harmless no-op.
    yafl_prof_thread_init();
    yafl_prof_enter(FN_ALPHA);
    yafl_prof_leave();
    yafl_prof_dump();
    CHECK(access(OUT_PATH, F_OK) != 0, "dump wrote a file before init");

    // Same order as a generated --profile main(): init, then thread_start.
    setenv("YAFL_PROF_FILE", OUT_PATH, 1);
    yafl_prof_init(TEST_FNS, FN_COUNT);
    thread_start(run_tests);
    return 1;   // unreachable: run_tests exits
}
