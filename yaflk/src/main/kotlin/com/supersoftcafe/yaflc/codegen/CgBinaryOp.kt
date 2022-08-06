package com.supersoftcafe.yaflc.codegen

enum class CgBinaryOp {
    ADD, FADD, SUB, FSUB, MUL, FMUL, DIV, FDIV, REM, FREM;

    override fun toString() = name.lowercase()
}