cmake_minimum_required(VERSION 3.27)
project(yaflc)

set(CMAKE_CXX_STANDARD 23)

add_executable(yaflc main.cpp
    examples/test.yafl examples/tryone.yafl
        tokenizer.cpp
        tokenizer.h
        parser.cpp
        parser.h
        error.cpp
        error.h)
