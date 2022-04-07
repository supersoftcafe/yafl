cmake_minimum_required(VERSION 3.21)
project(yaflcc)

set(CMAKE_CXX_STANDARD 20)

add_executable(yaflcc main.cpp Token.h TokenParser.cpp TokenParser.h Token.cpp Ast.cpp Ast.h GrammarParser.cpp GrammarParser.h TypeResolver.cpp TypeResolver.h CodeGenerator.cpp CodeGenerator.h Verifier.cpp Verifier.h)
