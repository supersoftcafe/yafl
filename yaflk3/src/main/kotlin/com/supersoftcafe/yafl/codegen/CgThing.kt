package com.supersoftcafe.yafl.codegen

sealed interface CgThing {
    fun toIr(context: CgContext): CgLlvmIr
}