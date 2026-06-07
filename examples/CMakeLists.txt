cmake_minimum_required(VERSION 3.19)
project(yafl_examples NONE)

# A standalone sample project: this is what building YAFL programs looks like for
# anyone with an installed toolchain. The ONLY dependency is the `yafl` compiler
# on the PATH — it finds the System library on its own search path (override with
# the YAFL_PATH environment variable) and statically links the runtime itself, so
# there are no headers, libraries, or C-compiler settings to configure here.
#
# Build it on its own, after installing the toolchain:
#     cmake -B build && cmake --build build
# (It is intentionally NOT part of the top-level YAFL build, which compiles the
# toolchain from source — these examples consume the *installed* tool.)

find_program(YAFL yafl REQUIRED)

# Compile one `<name>.yafl` to a runnable binary with `yafl`.  `-O2` selects a
# release build (optimised, dead runtime code dropped, stripped).
function(add_yafl_program name)
    set(SRC ${CMAKE_CURRENT_SOURCE_DIR}/${name}.yafl)
    set(BIN ${CMAKE_CURRENT_BINARY_DIR}/${name})
    add_custom_command(
        OUTPUT ${BIN}
        COMMAND ${YAFL} -O2 -o ${BIN} ${SRC}
        DEPENDS ${SRC}
        COMMENT "yafl -O2 -o ${name} ${name}.yafl"
        VERBATIM)
    # Target name differs from the output file name to avoid a self-dependency.
    add_custom_target(compile_${name} ALL DEPENDS ${BIN})
    install(PROGRAMS ${BIN} DESTINATION bin)
endfunction()

add_yafl_program(json_pretty)
