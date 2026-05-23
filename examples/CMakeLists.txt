cmake_minimum_required(VERSION 3.19)
project(yafl_examples LANGUAGES C)

# Each example .yafl is compiled to C by the in-tree compiler (run from
# source via python — no PyInstaller dependency), then compiled+linked
# here against the in-tree libyafl.so target.  The install rule places
# the binary at <prefix>/bin/yafl_<name>.

find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(YAFL_COMPILER_MAIN ${CMAKE_SOURCE_DIR}/compiler/main.py)

function(add_yafl_example name)
    set(SRC ${CMAKE_CURRENT_SOURCE_DIR}/${name}.yafl)
    set(GEN ${CMAKE_CURRENT_BINARY_DIR}/${name}.gen.c)
    add_custom_command(
        OUTPUT ${GEN}
        COMMAND ${Python3_EXECUTABLE} ${YAFL_COMPILER_MAIN} -O 2 -c ${GEN} ${SRC}
        DEPENDS ${SRC} ${YAFL_COMPILER_MAIN}
        COMMENT "yafl -c ${name}.yafl"
        VERBATIM
    )
    add_executable(yafl_${name} ${GEN})
    target_include_directories(yafl_${name}
        PRIVATE ${CMAKE_SOURCE_DIR}/yafllib)
    target_link_libraries(yafl_${name}
        PRIVATE yafl_shared m)
    install(TARGETS yafl_${name} RUNTIME DESTINATION bin)
endfunction()

add_yafl_example(json_pretty)
