cmake_minimum_required(VERSION 3.19)
project(yafl LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)   # strict ISO C (-std=c11), not gnu11; POSIX via feature-test macros in yafl.h

# Source files excluding main.c
set(SRC_FILES
    hash.c
    integer.c
    log.c
    once.c
    float.c
    io.c
    io_thread.c
    object.c
    gc_stats.c
    gc_debug.c
    primitive.c
    prof.c
    heapprof.c
    stackguard.c
    str.c
    task.c
    tempdir.c
    thread.c
    yafl.c
    lazy.c
    mmap.c
)

# Static library only — programs link the runtime statically, so there is no
# shared libyafl.so. The shipped runtime is held to a clean -Wall -Wextra -Werror
# bar under strict ISO C. main.c and the C test harnesses are held to the SAME
# bar: leaving them ungated let warnings accumulate silently, and each one that
# did turned out to mark a real defect (a discarded assertion, a main that never
# published argv, a `^` mis-parsed inside a `|`).
add_library(yafl_static STATIC ${SRC_FILES})
set_target_properties(yafl_static PROPERTIES OUTPUT_NAME yafl)
target_link_libraries(yafl_static PRIVATE m)
target_compile_options(yafl_static PRIVATE -Wall -Wextra -Werror)
# The shipped runtime is optimised (-O3) so every program that links it is fast
# and small, regardless of build type.
target_compile_options(yafl_static PRIVATE -O3)
# Optimised, so NDEBUG too: no asserts ship. A Debug configuration keeps them.
target_compile_definitions(yafl_static PRIVATE $<$<NOT:$<CONFIG:Debug>>:NDEBUG>)
# Per-function/data sections so a program linking the archive can drop the
# runtime functions it never reaches (clang -Wl,--gc-sections at link time).
target_compile_options(yafl_static PRIVATE -ffunction-sections -fdata-sections)

# Create executable with main.c
add_executable(yafl_exec main.c ${SRC_FILES})
target_link_libraries(yafl_exec PRIVATE m)
target_compile_options(yafl_exec PRIVATE -Wall -Wextra -Werror)

# The runtime is NOT installed to the C standard locations (lib/, include/).
# It ships only inside the System library at ${prefix}/lib/yafl/system.yl, which the
# top-level CMakeLists stages from the build-tree yafl_static archive + yafl.h.
# Programs are statically linked, so nothing yafl lands on clang's default paths.


# ---- Tests ----
enable_testing()

# Source files excluding main.c
set(TEST_SRC_FILES
    hash.c
    integer.c
    log.c
    once.c
    float.c
    io.c
    io_thread.c
    object.c
    gc_stats.c
    gc_debug.c
    primitive.c
    prof.c
    heapprof.c
    stackguard.c
    str.c
    task.c
    tempdir.c
    thread.c
    yafl.c
    lazy.c
    mmap.c
)

function(add_yafl_test name)
    add_executable(${name} tests/${name}.c ${TEST_SRC_FILES})
    target_include_directories(${name} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
    target_link_libraries(${name} PRIVATE m)
    target_compile_options(${name} PRIVATE -Wall -Wextra -Werror)
    add_test(NAME ${name} COMMAND ${name})
    # Run every C test with heap poisoning on: reclaimed objects are wiped with
    # 0x42 and the scanner aborts on any live->reclaimed edge, so a GC
    # use-after-free fails the suite deterministically instead of silently
    # reading stale memory. Production default is off (YAFL_GC_POISON unset).
    set_tests_properties(${name} PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1")
endfunction()

add_yafl_test(test_integer)
add_yafl_test(test_str)
add_yafl_test(test_once)
add_yafl_test(test_gc)
add_yafl_test(test_io)
add_yafl_test(test_task)
# test_backlog_zero: YAFL_TASK_BACKLOG=0 closes the pool to new work — the
# compilers' run-in-place / degrade-to-lazy tests rely on it.
add_yafl_test(test_backlog_zero)
set_tests_properties(test_backlog_zero PROPERTIES ENVIRONMENT "YAFL_TASK_BACKLOG=0")
add_yafl_test(test_io_stress)
add_yafl_test(test_gc_stress)
add_yafl_test(test_gc_min)
add_yafl_test(test_gc_step)
add_yafl_test(test_gc_ring)
# test_gc_min2: raw-pthread repro of the snapshot-smear window (a thread's
# allocations between cycle start and its own root scan land on pages taken
# into the current cycle, with no birth protection). Closed by the allocate-
# black-in-window guard in _object_alloc — this test is its regression test.
add_yafl_test(test_gc_min2)
# test_gc_min2_window: the same, with a 20 us sleep between storing a holder
# into its root slot and publishing it, so collections open inside that
# window. Publishing BEFORE the store, the old contract, failed every run:
# a cycle opening between the barrier's flag read and the store snapshotted
# the slot's previous occupant, and the holder — dropped from its thread's
# stack before that thread's take — was never marked. gc_root_publish now
# takes the slot and runs after the store.
add_executable(test_gc_min2_window tests/test_gc_min2.c ${TEST_SRC_FILES})
target_include_directories(test_gc_min2_window PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(test_gc_min2_window PRIVATE m)
target_compile_options(test_gc_min2_window PRIVATE -Wall -Wextra -Werror)
target_compile_definitions(test_gc_min2_window PRIVATE PUBLISH_WINDOW_NS=20000)
add_test(NAME test_gc_min2_window COMMAND test_gc_min2_window)
set_tests_properties(test_gc_min2_window PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1")
# test_gc_publish_step: the same window, stepped by hand. An object allocated
# before the cycle opens is stored into a root after the snapshot; only
# gc_root_publish marks it. (test_gc_step's object is allocated inside the
# opening window, so allocate-black marks it and that test cannot see the
# publish.) With the publish's shading removed, it reports the object
# reclaimed.
add_yafl_test(test_gc_publish_step)
# test_gc_lazy_step: the same window for a waiter CASed into a global lazy
# stub's flag root by lazy_enqueue_waiter. Unpublished, it is reclaimed while
# the flag still points at it.
add_yafl_test(test_gc_lazy_step)
# test_gc_tagged_task: a task referenced only by a TASK-tagged word — a pending
# result, in a heap field or a stack slot — survives a cycle.
add_yafl_test(test_gc_tagged_task)
# All three drive the collector by hand on one thread.
set_tests_properties(test_gc_publish_step test_gc_lazy_step test_gc_tagged_task PROPERTIES ENVIRONMENT
    "YAFL_GC_POISON=1;YAFL_THREADS=1")
# test_gc_gen: stepped test of immutability-based generations — promotion after
# GC_PROMOTE_AFTER prunes, exemption from minors, reclamation by a major.
add_yafl_test(test_gc_gen)
# test_gc_old_late_write: stepped. A late write into an old page between the
# cycle's START and the writer's own root scan is traced only because the end
# of SCAN_ROOTS demotes the pages late writes touched; without that the value
# is reclaimed while the old object points at it.
add_yafl_test(test_gc_old_late_write)
set_tests_properties(test_gc_old_late_write PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;YAFL_THREADS=1")
# test_gc_dirty_compact: stepped. A dirty-old page that an old page points
# into is not compacted in a minor: the old referrer is not traced, so it
# would keep a forwarder's address while the forwarder's slot is reclaimed.
add_yafl_test(test_gc_dirty_compact)
set_tests_properties(test_gc_dirty_compact PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;YAFL_THREADS=1")
# test_gc_dwell: once a cycle ends, the next opens only after the dwell's
# pages have been allocated (natural pacing, one worker).
add_yafl_test(test_gc_dwell)
set_tests_properties(test_gc_dwell PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;YAFL_THREADS=1")
# test_gc_write_once_step: stepped. While a cycle marks, a store that
# overwrites nothing stays inline only once its thread's root scan is done;
# before it, the store owes the insertion half and calls out.
add_yafl_test(test_gc_write_once_step)
set_tests_properties(test_gc_write_once_step PROPERTIES ENVIRONMENT
    "YAFL_GC_POISON=1;YAFL_THREADS=1")
# test_gc_misaligned_root: stepped. An object referenced only by a pointer at
# a misaligned stack address (an optimiser's aggregate slice can put one at
# 4 mod 8) survives full cycles: the conservative stack scan looks at every
# byte offset, not only word-aligned ones.
add_yafl_test(test_gc_misaligned_root)
set_tests_properties(test_gc_misaligned_root PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;YAFL_THREADS=1")
# test_gc_pressure: a ratcheting live set plus churn whose objects live a few
# cycles before dying, in a deliberately small heap. Guards the near-full
# machinery: the pressure backstop in gc_page_alloc, the relocation reserve,
# and majors demoting DIRTY old pages (whose force-mark otherwise retains
# their garbage forever — the bug that made yspell abort in any heap < 1 GiB).
add_yafl_test(test_gc_pressure)
# test_gc_stale_mark: remote conservative marks from stale stack words, aimed
# at objects that die and are pruned in between. A mark must never bring a
# dead slot back, nor lead the marker into one.
add_yafl_test(test_gc_stale_mark)
add_test(NAME test_gc_stale_mark_poison COMMAND test_gc_stale_mark)
set_tests_properties(test_gc_stale_mark_poison PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1")
# The collector dwells between cycles (YAFL_GC_IDLE_PAGES), so a small test
# sees few cycles. The _eager variants run cycles back to back, poisoned, so
# the GC tests keep crossing as many cycle boundaries as their work allows.
foreach(t test_gc test_gc_stress test_gc_ring test_gc_min test_gc_min2 test_gc_pressure test_gc_gen test_gc_late_pin_race test_pin test_large_objects test_str test_io_stress)
    add_test(NAME ${t}_eager COMMAND ${t})
    set_tests_properties(${t}_eager PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;YAFL_GC_IDLE_PAGES=0")
endforeach()
# test_gc_mesh: every worker mutates and reads one shared graph within the
# sharing contract — mutable cells under their pin, immutable mailboxes read
# lock-free and filled write-once (yafl_cas_once) — trading young chains
# between workers. Aimed at weakly-ordered machines; the soak script
# (tests/gc_soak.py) runs it long.
add_yafl_test(test_gc_mesh)
set_tests_properties(test_gc_mesh PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;MESH_STEPS=50000")
add_test(NAME test_gc_mesh_eager COMMAND test_gc_mesh)
set_tests_properties(test_gc_mesh_eager PROPERTIES ENVIRONMENT
    "YAFL_GC_POISON=1;YAFL_GC_IDLE_PAGES=0;MESH_STEPS=50000")
# test_gc_fwd_chain: compaction forwarding chains (A -> B -> C via a head stub
# pinned by a conservative stack slot) must path-compress when scanned — the
# head's forward word snaps to the tail and the bypassed middle stub's page
# is reclaimed.
add_yafl_test(test_gc_fwd_chain)
# test_gc_step2: single-stepped transitive (root->holder->child) scenario; it
# PASSES, but only because the conservative stack/register scan leaks the
# child's address — it cannot demonstrate the hazard it describes. Kept in
# tests/ as documentation, not registered.
add_yafl_test(test_parallel)
add_yafl_test(test_prof)
add_yafl_test(test_heapprof)
add_yafl_test(test_heapprof2)
add_yafl_test(test_heapprof3)
add_yafl_test(test_tempdir)
add_yafl_test(test_mmap)
add_yafl_test(test_large_objects)
add_yafl_test(test_pin)
add_yafl_test(test_vtable_lookup)
# test_gc_late_pin_race: a late pin racing its object's page into the old
# generation. Builds its own object.c with YAFL_GC_RACE_PROBE, which hooks the
# two windows of the promotion — before the OLD stamps (the pin's fast path,
# caught by the stamp's re-check) and after them (the pin reports the write) —
# so the test can land a late write in either deterministically. Without the
# protocol the page promotes holding an untraced young edge and the next minor
# reclaims the referent.
add_yafl_test(test_gc_late_pin_race)
target_compile_definitions(test_gc_late_pin_race PRIVATE YAFL_GC_RACE_PROBE=1)
set_tests_properties(test_gc_late_pin_race PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;RACE_WINDOW=1")
add_test(NAME test_gc_late_pin_race_unstamped COMMAND test_gc_late_pin_race)
set_tests_properties(test_gc_late_pin_race_unstamped PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;RACE_WINDOW=0")
# test_lazy_runner: exactly one caller of lazy_acquire holds the gate, and
# every waiter is completed, even when the holder releases between a waiter's
# enqueue and its return. Builds its own lazy.c with YAFL_LAZY_RACE_PROBE,
# which hooks that window.
add_yafl_test(test_lazy_runner)
target_compile_definitions(test_lazy_runner PRIVATE YAFL_LAZY_RACE_PROBE=1)
# test_gc_static_store: stepped. A store into a static object (a global's lazy
# stub) whose barrier ran before the cycle opened is seen only because the
# object store macros publish after the store when the container is outside
# the heap.
add_yafl_test(test_gc_static_store)
set_tests_properties(test_gc_static_store PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;YAFL_THREADS=1")
# test_gc_late_requeue: stepped. A rescan request that arrives after marking
# has retired must not take its page out of the cycle's prune. Builds its own
# object.c with YAFL_GC_RETIRE_PROBE, which hooks the moment marking retires.
add_yafl_test(test_gc_late_requeue)
target_compile_definitions(test_gc_late_requeue PRIVATE YAFL_GC_RETIRE_PROBE=1)
set_tests_properties(test_gc_late_requeue PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;YAFL_THREADS=1")
# test_gc_pump_window: stepped. A rescan request a pump has taken off the
# reprocess ring, but not yet delivered, must keep marking from retiring.
# Builds its own object.c with YAFL_GC_PUMP_PROBE, which hooks that window.
add_yafl_test(test_gc_pump_window)
target_compile_definitions(test_gc_pump_window PRIVATE YAFL_GC_PUMP_PROBE=1)
set_tests_properties(test_gc_pump_window PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;YAFL_THREADS=1")
# test_gc_overflow_window: stepped. A mark the full reprocess ring drops after
# the tail has read the overflow flag must keep marking from retiring. Builds
# its own object.c with YAFL_GC_OVERFLOW_PROBE, which hooks that window.
add_yafl_test(test_gc_overflow_window)
target_compile_definitions(test_gc_overflow_window PRIVATE YAFL_GC_OVERFLOW_PROBE=1)
set_tests_properties(test_gc_overflow_window PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;YAFL_THREADS=1")
# test_gc_writer_window: stepped. A mutator between setting a mark bit and
# pushing the page on the reprocess ring must keep marking from retiring.
# Builds its own object.c with YAFL_GC_WRITER_PROBE, which hooks that window.
add_yafl_test(test_gc_writer_window)
target_compile_definitions(test_gc_writer_window PRIVATE YAFL_GC_WRITER_PROBE=1)
set_tests_properties(test_gc_writer_window PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1;YAFL_THREADS=1")

