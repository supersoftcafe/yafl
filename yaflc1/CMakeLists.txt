cmake_minimum_required(VERSION 3.22)
project(yaflc1 C)

set(CMAKE_C_STANDARD 11)
SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fomit-frame-pointer")
set(SOURCE_FILES main.c fiber.c fiber.h context.c queue.c context.h queue.h blitz.h blitz.c heap.c heap.h object.c object.h)

add_library(yaflc1 ${SOURCE_FILES})
