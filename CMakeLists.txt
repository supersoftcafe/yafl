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
if(UNITTEST_PARALLEL)
    set(YAFL_SUITE_CMD ${UNITTEST_PARALLEL} -j 3)
else()
    set(YAFL_SUITE_CMD ${Python3_EXECUTABLE} -m unittest discover)
endif()

add_test(NAME compiler_suite
    COMMAND ${CMAKE_COMMAND} -E env YAFL_LIBYAFL_A=$<TARGET_FILE:yafl_static> ${YAFL_SUITE_CMD}
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/compiler)
set_tests_properties(compiler_suite PROPERTIES TIMEOUT 1800)

# Convenience: `cmake --build build --target check` builds everything (so the
# runtime archive and the C test executables exist) then runs the whole CTest set.
add_custom_target(check
    COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR}
    COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
    USES_TERMINAL)
