cmake_minimum_required(VERSION 3.27)
project(yaflc)

set(CMAKE_CXX_STANDARD 23)

add_executable(yaflc main.cpp
    examples/test.yafl examples/tryone.yafl
        parse2.cpp
        parse2.h
        error.cpp
        error.h)
