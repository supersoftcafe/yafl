package com.supersoftcafe.yafl.codegen

enum class CgBinaryOp {
    ADD, FADD, SUB, FSUB, MUL, FMUL, DIV, FDIV, REM, FREM, ICMP_EQ;

    override fun toString() = name.lowercase().replace('_', ' ')
}