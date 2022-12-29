package com.supersoftcafe.yaflc.codegen

sealed interface CgType {
    val llvmType: String
}
