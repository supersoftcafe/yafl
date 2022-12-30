package com.supersoftcafe.yafl.codegen

enum class CgBinaryOp {
    ADD, FADD, SUB, FSUB, MUL, FMUL, SDIV, FDIV, SREM, FREM, ICMP_EQ, ICMP_SLT;

    override fun toString() = name.lowercase().replace('_', ' ')
}