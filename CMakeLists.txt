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
add_test(NAME bootstrap_binary
    COMMAND ${CMAKE_COMMAND} -E env YAFL_LIBYAFL_A=$<TARGET_FILE:yafl_static>
            PYTHONHASHSEED=0
            ${Python3_EXECUTABLE} build_bootstrap.py -o ${YAFL_BOOTSTRAP_BIN}
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/compiler)
set_tests_properties(bootstrap_binary PROPERTIES
    TIMEOUT 3600
    FIXTURES_SETUP bootstrap_bin)

# PYTHONHASHSEED=0 is REQUIRED, not a nicety: the seven test_bootstrap_c_*
# modules assert it in setUpClass and error out without it. Because that is a
# setUpClass failure rather than a test failure, the suite still reported a
# result — so the byte-parity C comparison across -O0..-O3, the compiler's core
# contract, silently never ran under ctest at all. It only ever ran when the
# suite was invoked by hand from a shell that already exported the variable.
add_test(NAME compiler_suite
    COMMAND ${CMAKE_COMMAND} -E env YAFL_LIBYAFL_A=$<TARGET_FILE:yafl_static>
            YAFL_BOOTSTRAP_BIN=${YAFL_BOOTSTRAP_BIN}
            PYTHONHASHSEED=0 ${YAFL_SUITE_CMD}
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/compiler)
# `unittest-parallel` exits 0 even when it discovers *zero* tests (printing
# "(0 total tests)" / "Ran 0 test"), which would silently report success if the
# suite ever failed to be found. Treat an empty run as a failure regardless of
# exit code — this is what makes a misdiscovered suite show up as a failure.
set_tests_properties(compiler_suite PROPERTIES
    # 4h. It was 1800s, which is LESS than the suite takes (~112 min at -j 3),
    # so the gate reported a timeout rather than a result — a red run that says
    # nothing about the code. Keep this comfortably above the real duration.
    TIMEOUT 14400
    FAIL_REGULAR_EXPRESSION "Ran 0 test;NO TESTS RAN;\\(0 total tests\\)")

set_tests_properties(compiler_suite PROPERTIES FIXTURES_REQUIRED bootstrap_bin)

# THE SELF-COMPILE, LAST. The suite says the compiler is correct on small
# programs; this says it survives the real one — its own sources, the hardest
# input there is. It reaches codegen paths, GC behaviour under a compiler-sized
# workload and any residual nondeterminism that small programs never touch, so
# a failure here with a green suite means the problem only appears at scale.
# RUN_SERIAL because it wants the machine (and a compiler-sized heap) to itself.
add_test(NAME self_compile
    COMMAND ${CMAKE_COMMAND} -E env YAFL_BOOTSTRAP_BIN=${YAFL_BOOTSTRAP_BIN}
            ${Python3_EXECUTABLE} selfcompile.py
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/compiler)
set_tests_properties(self_compile PROPERTIES
    TIMEOUT 14400
    RUN_SERIAL TRUE
    FIXTURES_REQUIRED bootstrap_bin
    DEPENDS compiler_suite)

# ── stdlib unit tests, written in YAFL ───────────────────────────────────────
# compiler/stdlib_tests/ holds `[test]` functions exercising the stdlib. They
# live OUTSIDE compiler/stdlib/ deliberately: the System library is assembled
# from every file in that directory as ONE library, so a test file there would
# be parsed into every compilation in the tree — every application paying to
# carry tests it never runs. APPLICATION code should keep its tests beside the
# source they test, even in the same file; a library cannot, for this reason.
#
# Two steps, because building the binary and running it fail for different
# reasons and should be told apart: a compile error in the tests is not the
# same event as a stdlib regression.
set(YAFL_STDLIB_TESTS_BIN ${CMAKE_BINARY_DIR}/stdlib_tests)
add_test(NAME stdlib_tests_build
    COMMAND ${CMAKE_COMMAND} -E env YAFL_LIBYAFL_A=$<TARGET_FILE:yafl_static>
            PYTHONHASHSEED=0
            ${Python3_EXECUTABLE} main.py -O0 --test
            -o ${YAFL_STDLIB_TESTS_BIN} stdlib_tests
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/compiler)
set_tests_properties(stdlib_tests_build PROPERTIES
    TIMEOUT 3600
    FIXTURES_SETUP stdlib_tests_bin)

add_test(NAME stdlib_tests COMMAND ${YAFL_STDLIB_TESTS_BIN})
set_tests_properties(stdlib_tests PROPERTIES
    TIMEOUT 600
    FIXTURES_REQUIRED stdlib_tests_bin
    # The runner exits 0 only when every test passed, but a binary that ran
    # NOTHING would also exit 0 — the same hole the compiler_suite guard
    # closes. Require at least ONE pass: `[0-9]+` would match "0 passed, 0
    # failed", which is precisely the case this is here to catch.
    PASS_REGULAR_EXPRESSION "[1-9][0-9]* passed, 0 failed")

# Convenience: `cmake --build build --target check` builds everything (so the
# runtime archive and the C test executables exist) then runs the whole CTest set.
add_custom_target(check
    COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR}
    COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
    USES_TERMINAL)
