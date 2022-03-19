cmake_minimum_required(VERSION 3.21)
project(yaflirc)

set(CMAKE_CXX_STANDARD 17)

add_executable(yaflirc main.cpp parser.cpp parser.h types.h types.cpp input.cpp input.h methodbuilder.cpp methodbuilder.h)
