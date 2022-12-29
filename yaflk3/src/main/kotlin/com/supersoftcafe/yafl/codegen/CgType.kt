package com.supersoftcafe.yafl.codegen

sealed interface CgType {
    val llvmType: String
}
