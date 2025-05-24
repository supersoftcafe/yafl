cmake_minimum_required(VERSION 3.0)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

project(yaflcore LANGUAGES C)

add_executable(yaflcore main.c integer.c object.c primitive.c string.c thread.c yafl.c)

install(TARGETS yaflcore RUNTIME DESTINATION bin)
