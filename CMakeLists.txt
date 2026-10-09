cmake_minimum_required(VERSION 3.19)
project(yafl_meta LANGUAGES C)

# Top-level driver.  Build everything with:
#   cmake -B build -DCMAKE_INSTALL_PREFIX=/usr/local
#   cmake --build build -j
#   cmake --install build
#
# This builds:
#   - yafllib       → libyafl.so / libyafl.a / yafl.h
#   - compiler      → yafl  (PyInstaller)
#   - System lib    → lib/yafl/system.yl  (.yl zip: yafl.toml + stdlib sources + yafl.h + libyafl.a)
# and installs them under ${CMAKE_INSTALL_PREFIX}.  The compiler finds libraries
# under ${CMAKE_INSTALL_PREFIX}/lib/yafl (override with the YAFL_PATH env var).
#
# `examples/` is deliberately NOT built here: it is a standalone sample project
# that consumes the *installed* `yafl`, so build it separately after installing
# (cd examples && cmake -B build && cmake --build build).

add_subdirectory(yafllib)
add_subdirectory(compiler)

# ── System library staging & install ──────────────────────────────────────────
# Assemble a self-contained System library: the stdlib YAFL sources, a generated
# manifest, and copies of yafl.h + libyafl.a beside them. Identical in the build
# tree and once installed, so the compiler resolves `System` the same way in both.
find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(YAFL_SYSTEM_YL ${CMAKE_BINARY_DIR}/stage/system.yl)
add_custom_target(package_system_library ALL
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/compiler/libraries.py package-system
            ${YAFL_SYSTEM_YL}
            ${CMAKE_SOURCE_DIR}/compiler/stdlib
            ${CMAKE_SOURCE_DIR}/yafllib/yafl.h
            $<TARGET_FILE:yafl_static>
    DEPENDS yafl_static
    COMMENT "Packaging the System library (system.yl)")

# Installed as a single .yl zip: ${prefix}/lib/yafl/system.yl
install(FILES ${YAFL_SYSTEM_YL} DESTINATION lib/yafl)

# System::Test — the `--test` runner — ships beside System, staged and installed
# the same way. Before this an installed compiler could not build a test binary
# at all: only the from-source Python compiler found it, through its dev
# fallback into compiler/libs/.
set(YAFL_STAGE_DIR ${CMAKE_BINARY_DIR}/stage)
add_custom_target(stage_system_test ALL
    COMMAND ${CMAKE_COMMAND} -E copy_directory
            ${CMAKE_SOURCE_DIR}/compiler/libs/system-test ${YAFL_STAGE_DIR}/system-test
    COMMENT "Staging the System::Test library")
install(DIRECTORY ${CMAKE_SOURCE_DIR}/compiler/libs/system-test DESTINATION lib/yafl)

# ── Tests ─────────────────────────────────────────────────────────────────────
# The Python compiler suite is registered as a CTest test, run against the
# runtime archive THIS build produced (via YAFL_LIBYAFL_A) so it never picks up a
# stale libyafl.a. Prefer unittest-parallel if present; fall back to stdlib
# unittest. `ctest` also runs the yafllib C unit tests registered in yafllib/.
enable_testing()
find_program(UNITTEST_PARALLEL unittest-parallel)
# Discovery is pinned to `-s tests -t .` (the suite lives in compiler/tests) so
# it never depends on the runner's default start directory or the cwd.
if(UNITTEST_PARALLEL)
    # -j 0 = all cores. Never a fixed number: it was -j 3 on a 5-core box,
    # which under-subscribed here and would over-subscribe a smaller one.
    set(YAFL_SUITE_CMD ${UNITTEST_PARALLEL} -j 0 -s tests -t .)
else()
    set(YAFL_SUITE_CMD ${Python3_EXECUTABLE} -m unittest discover -s tests -t .)
endif()

# The port binary is an INPUT to the suite, not something the tests build: ~25
# modules execute it, and having the first one to ask for it compile the port
# (~10 minutes) while the rest blocked on a lock serialised the parallel run.
# It is produced once here, as a fixture the suite depends on.
set(YAFL_BOOTSTRAP_BIN ${CMAKE_BINARY_DIR}/ybootstrap)
# The C the port was linked from — kept for the self-compile at the end, which
# must reproduce it byte for byte.
set(YAFL_BOOTSTRAP_C ${CMAKE_BINARY_DIR}/ybootstrap.c)

# TWO SPEEDS, the slow one opt-in. `full` is the regression: the Python compiler builds the port,
# the Python suite runs, and every [test] folder is built and run at every
# level. `fast` is for PRs and for the middle of a sequence of changes: the
# folders at -O3 only, no Python suite, and the port's Python build is reused
# while the Python compiler is unchanged (build_bootstrap.py --reuse). Both end
# with the self-compile, which must reproduce the C the port was built from.
#
#   cmake -B build -DYAFL_TEST_SPEED=full
set(YAFL_TEST_SPEED fast CACHE STRING "Test path: fast, or full (the regression)")
set_property(CACHE YAFL_TEST_SPEED PROPERTY STRINGS fast full)
if(YAFL_TEST_SPEED STREQUAL "full")
    set(YAFL_TEST_LEVELS 0 1 2 3)
    set(YAFL_BOOTSTRAP_REUSE)
elseif(YAFL_TEST_SPEED STREQUAL "fast")
    set(YAFL_TEST_LEVELS 3)
    set(YAFL_BOOTSTRAP_REUSE --reuse -L ${YAFL_STAGE_DIR})
else()
    message(FATAL_ERROR "YAFL_TEST_SPEED must be full or fast, not '${YAFL_TEST_SPEED}'")
endif()

add_test(NAME bootstrap_binary
    COMMAND ${CMAKE_COMMAND} -E env YAFL_LIBYAFL_A=$<TARGET_FILE:yafl_static>
            PYTHONHASHSEED=0
            ${Python3_EXECUTABLE} build_bootstrap.py -o ${YAFL_BOOTSTRAP_BIN}
            --c-output ${YAFL_BOOTSTRAP_C} ${YAFL_BOOTSTRAP_REUSE}
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/compiler)
set_tests_properties(bootstrap_binary PROPERTIES
    TIMEOUT 3600
    FIXTURES_SETUP bootstrap_bin)

# THE COMPILER UNDER TEST. The port and the Python compiler have parity, so
# either is a drop-in replacement for the other: every behaviour test — the
# Python suite's compile-and-run tests and the YAFL `[test]` folders — runs
# against the one chosen here, through its command line.
#
#   cmake -B build -DYAFL_TEST_COMPILER=python
set(YAFL_TEST_COMPILER port CACHE STRING
    "Compiler the behaviour tests drive: port (build/ybootstrap) or python (main.py)")
set_property(CACHE YAFL_TEST_COMPILER PROPERTY STRINGS port python)
if(YAFL_TEST_COMPILER STREQUAL "port")
    set(YAFL_TEST_COMPILER_CMD ${YAFL_BOOTSTRAP_BIN})
elseif(YAFL_TEST_COMPILER STREQUAL "python")
    set(YAFL_TEST_COMPILER_CMD ${CMAKE_COMMAND} -E env PYTHONHASHSEED=0
                               ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/compiler/main.py)
else()
    message(FATAL_ERROR "YAFL_TEST_COMPILER must be port or python, not '${YAFL_TEST_COMPILER}'")
endif()

if(YAFL_TEST_SPEED STREQUAL "full")
    # PYTHONHASHSEED=0 is REQUIRED, not a nicety: the seven test_bootstrap_c_*
    # modules assert it in setUpClass and error out without it. Because that is a
    # setUpClass failure rather than a test failure, the suite still reported a
    # result — so the byte-parity C comparison across -O0..-O3, the compiler's core
    # contract, silently never ran under ctest at all. It only ever ran when the
    # suite was invoked by hand from a shell that already exported the variable.
    add_test(NAME compiler_suite
        COMMAND ${CMAKE_COMMAND} -E env YAFL_LIBYAFL_A=$<TARGET_FILE:yafl_static>
                YAFL_BOOTSTRAP_BIN=${YAFL_BOOTSTRAP_BIN}
                YAFL_COMPILER=${YAFL_TEST_COMPILER}
                PYTHONHASHSEED=0 ${YAFL_SUITE_CMD}
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/compiler)
    # `unittest-parallel` exits 0 even when it discovers *zero* tests (printing
    # "(0 total tests)" / "Ran 0 test"), which would silently report success if the
    # suite ever failed to be found. Treat an empty run as a failure regardless of
    # exit code — this is what makes a misdiscovered suite show up as a failure.
    set_tests_properties(compiler_suite PROPERTIES
        # 6h, comfortably above the real duration even on a slow 2-vCPU CI runner.
        # It was 1800s, which is LESS than the suite takes (~112 min at -j 3),
        # so the gate reported a timeout rather than a result — a red run that says
        # nothing about the code. Keep this comfortably above the real duration.
        TIMEOUT 21600
        FAIL_REGULAR_EXPRESSION "Ran 0 test;NO TESTS RAN;\\(0 total tests\\)")

    set_tests_properties(compiler_suite PROPERTIES FIXTURES_REQUIRED bootstrap_bin)
    set(YAFL_SUITE_TEST compiler_suite)
endif()


# ── unit tests written in YAFL ───────────────────────────────────────────────
# A folder of `.yafl` files holding `[test]` functions becomes ONE test binary
# (`--test`), built by the compiler under test against the staged libraries.
# Each file is its own unit with its own namespace: a compile error names its
# file, and the runner runs — and can select — each test on its own.
#
#   compiler/stdlib_tests/  the stdlib. OUTSIDE compiler/stdlib/ deliberately:
#                           the System library is every file in that directory,
#                           so a test there would be carried by every program.
#   compiler/yafl_tests/    the compiler: behaviour checked by running code.
#
# Two steps, because building the binary and running it fail for different
# reasons and should be told apart: a compile error in the tests is not the
# same event as a regression.
function(yafl_test_folder name folder opt)
    set(bin ${CMAKE_BINARY_DIR}/${name})
    add_test(NAME ${name}_build
        COMMAND ${YAFL_TEST_COMPILER_CMD} -O${opt} -L ${YAFL_STAGE_DIR} --test
                -o ${bin} ${folder}
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/compiler)
    set_tests_properties(${name}_build PROPERTIES
        TIMEOUT 3600
        FIXTURES_REQUIRED bootstrap_bin
        FIXTURES_SETUP ${name}_bin)
    add_test(NAME ${name} COMMAND ${bin})
    set_tests_properties(${name} PROPERTIES
        TIMEOUT 600
        FIXTURES_REQUIRED ${name}_bin
        # The runner exits 0 only when every test passed, but a binary that ran
        # NOTHING would also exit 0 — the same hole the compiler_suite guard
        # closes. Require at least ONE pass: `[0-9]+` would match "0 passed,
        # 0 failed", which is precisely the case this is here to catch.
        PASS_REGULAR_EXPRESSION "[1-9][0-9]* passed, 0 failed")
endfunction()

# Each folder runs at every level of the path's YAFL_TEST_LEVELS: each level
# switches passes on (inliner, small-function inlining, single-caller fold),
# and -O0 keeps the runtime's asserts and poison hooks. The fast path's one
# level is -O3, the level that transforms the most.
set(YAFL_FOLDER_TESTS)
foreach(folder stdlib_tests yafl_tests)
    foreach(opt ${YAFL_TEST_LEVELS})
        yafl_test_folder(${folder}_o${opt} ${folder} ${opt})
        list(APPEND YAFL_FOLDER_TESTS ${folder}_o${opt})
    endforeach()
endforeach()

# ── THE SELF-COMPILE, LAST ───────────────────────────────────────────────────
# ONE self-compile, after everything else. The suite says the compiler is
# correct on small programs; this says it survives the real one — its own
# sources, the hardest input there is — and the check is the strongest one
# available: the port compiles its own sources through its command line and
# must emit, byte for byte, the C the PYTHON compiler emitted for the same
# sources when it built the port at the start. On the fast path, when the
# port's sources changed since the cached Python build, that C came from the
# Python-built port instead: the new port must agree with it. RUN_SERIAL
# because it wants the machine (and a compiler-sized heap) to itself.
set(YAFL_SELF_COMPILE_AFTER ${YAFL_SUITE_TEST} ${YAFL_FOLDER_TESTS})
add_test(NAME self_compile
    COMMAND ${Python3_EXECUTABLE} selfcompile.py --binary ${YAFL_BOOTSTRAP_BIN}
            -L ${YAFL_STAGE_DIR} --expect ${YAFL_BOOTSTRAP_C}
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/compiler)
set_tests_properties(self_compile PROPERTIES
    TIMEOUT 14400
    RUN_SERIAL TRUE
    FIXTURES_REQUIRED bootstrap_bin
    DEPENDS "${YAFL_SELF_COMPILE_AFTER}")

# Convenience: `cmake --build build --target check` builds everything (so the
# runtime archive and the C test executables exist) then runs the whole CTest set.
add_custom_target(check
    COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR}
    COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
    USES_TERMINAL)
