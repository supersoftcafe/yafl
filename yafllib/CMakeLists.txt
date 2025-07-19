cmake_minimum_required(VERSION 3.19)
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

# Create static library
add_library(yaflcore_static STATIC ${SRC_FILES})
set_target_properties(yaflcore_static PROPERTIES OUTPUT_NAME yaflcore)

# Create executable with main.c
add_executable(yaflcore_exec main.c ${SRC_FILES})

# Install targets
install(TARGETS yaflcore_shared LIBRARY DESTINATION lib)

install(TARGETS yaflcore_static ARCHIVE DESTINATION lib)

# install(TARGETS yaflcore_exec RUNTIME DESTINATION bin)

# Optionally install headers
install(FILES yafl.h DESTINATION include/yaflcore)

