cmake_minimum_required(VERSION 3.19)
project(yafl LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Source files excluding main.c
set(SRC_FILES
    integer.c
    float.c
    io.c
    io_thread.c
    object.c
    primitive.c
    string.c
    task.c
    thread.c
    yafl.c
    lazy.c
    mmap.c
)

# Create shared library
add_library(yafl_shared SHARED ${SRC_FILES})
set_target_properties(yafl_shared PROPERTIES OUTPUT_NAME yafl)
target_link_libraries(yafl_shared PRIVATE m)

# Create static library
add_library(yafl_static STATIC ${SRC_FILES})
set_target_properties(yafl_static PROPERTIES OUTPUT_NAME yafl)
target_link_libraries(yafl_static PRIVATE m)

# Create executable with main.c
add_executable(yafl_exec main.c ${SRC_FILES})
target_link_libraries(yafl_exec PRIVATE m)

# Install targets
install(TARGETS yafl_shared LIBRARY DESTINATION lib)

install(TARGETS yafl_static ARCHIVE DESTINATION lib)

# install(TARGETS yafl_exec RUNTIME DESTINATION bin)

# Optionally install headers
install(FILES yafl.h DESTINATION include)


# ---- Tests ----
enable_testing()

# Source files excluding main.c
set(TEST_SRC_FILES
    integer.c
    float.c
    io.c
    io_thread.c
    object.c
    primitive.c
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
endfunction()

add_yafl_test(test_integer)
add_yafl_test(test_string)
add_yafl_test(test_gc)
add_yafl_test(test_io)
add_yafl_test(test_task)
add_yafl_test(test_io_stress)
add_yafl_test(test_gc_stress)
add_yafl_test(test_gc_min)

