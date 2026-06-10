cmake_minimum_required(VERSION 3.19)
project(yafl LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)   # strict ISO C (-std=c11), not gnu11; POSIX via feature-test macros in yafl.h

# Source files excluding main.c
set(SRC_FILES
    hash.c
    integer.c
    float.c
    io.c
    io_thread.c
    object.c
    parallel.c
    primitive.c
    stackguard.c
    string.c
    task.c
    thread.c
    yafl.c
    lazy.c
    mmap.c
)

# Static library only — programs link the runtime statically, so there is no
# shared libyafl.so. The shipped runtime is held to a clean -Wall -Wextra -Werror
# bar under strict ISO C. (main.c and the C test harnesses below are dev-only and
# not gated.)
add_library(yafl_static STATIC ${SRC_FILES})
set_target_properties(yafl_static PROPERTIES OUTPUT_NAME yafl)
target_link_libraries(yafl_static PRIVATE m)
target_compile_options(yafl_static PRIVATE -Wall -Wextra -Werror)
# The shipped runtime is optimised (-O3) so every program that links it is fast
# and small, regardless of build type.
target_compile_options(yafl_static PRIVATE -O3)
# Per-function/data sections so a program linking the archive can drop the
# runtime functions it never reaches (clang -Wl,--gc-sections at link time).
target_compile_options(yafl_static PRIVATE -ffunction-sections -fdata-sections)

# Create executable with main.c
add_executable(yafl_exec main.c ${SRC_FILES})
target_link_libraries(yafl_exec PRIVATE m)

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
    float.c
    io.c
    io_thread.c
    object.c
    parallel.c
    primitive.c
    stackguard.c
    string.c
    task.c
    thread.c
    yafl.c
    lazy.c
    mmap.c
)

function(add_yafl_test name)
    add_executable(${name} tests/${name}.c ${TEST_SRC_FILES})
    target_include_directories(${name} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
    target_link_libraries(${name} PRIVATE m)
    add_test(NAME ${name} COMMAND ${name})
    # Run every C test with heap poisoning on: reclaimed objects are wiped with
    # 0x42 and the scanner aborts on any live->reclaimed edge, so a GC
    # use-after-free fails the suite deterministically instead of silently
    # reading stale memory. Production default is off (YAFL_GC_POISON unset).
    set_tests_properties(${name} PROPERTIES ENVIRONMENT "YAFL_GC_POISON=1")
endfunction()

add_yafl_test(test_integer)
add_yafl_test(test_string)
add_yafl_test(test_gc)
add_yafl_test(test_io)
add_yafl_test(test_task)
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
# test_gc_step2: single-stepped transitive (root->holder->child) scenario; it
# PASSES, but only because the conservative stack/register scan leaks the
# child's address — it cannot demonstrate the hazard it describes. Kept in
# tests/ as documentation, not registered.
add_yafl_test(test_parallel)
add_yafl_test(test_mmap)
add_yafl_test(test_large_objects)

