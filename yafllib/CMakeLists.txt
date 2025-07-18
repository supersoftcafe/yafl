cmake_minimum_required(VERSION 3.10)
project(yaflcore LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Source files excluding main.c
set(SRC_FILES
    integer.c
    object.c
    primitive.c
    string.c
    thread.c
    yafl.c
)

# Create shared library
add_library(yaflcore_shared SHARED ${SRC_FILES})
set_target_properties(yaflcore_shared PROPERTIES OUTPUT_NAME yaflcore)
set_target_properties(yaflcore_shared PROPERTIES ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib
                                               LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

# Create static library
add_library(yaflcore_static STATIC ${SRC_FILES})
set_target_properties(yaflcore_static PROPERTIES OUTPUT_NAME yaflcore)
set_target_properties(yaflcore_static PROPERTIES ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib
                                               LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

# Create executable with main.c
add_executable(yaflcore_exec main.c ${SRC_FILES})
set_target_properties(yaflcore_exec PROPERTIES RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# No install() command required
