package com.supersoftcafe.yafl.models.llir

sealed interface CgThing {
    fun toIr(context: CgContext): CgLlvmIr
}