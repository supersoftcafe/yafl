cmake_minimum_required(VERSION 3.19)
project(yafl LANGUAGES C)

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
add_library(yafl_shared SHARED ${SRC_FILES})
set_target_properties(yafl_shared PROPERTIES OUTPUT_NAME yafl)

# Create static library
add_library(yafl_static STATIC ${SRC_FILES})
set_target_properties(yafl_static PROPERTIES OUTPUT_NAME yafl)

# Create executable with main.c
add_executable(yafl_exec main.c ${SRC_FILES})

# Install targets
install(TARGETS yafl_shared LIBRARY DESTINATION lib)

install(TARGETS yafl_static ARCHIVE DESTINATION lib)

# install(TARGETS yafl_exec RUNTIME DESTINATION bin)

# Optionally install headers
install(FILES yafl.h DESTINATION include)

