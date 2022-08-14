package com.supersoftcafe.yaflc.codegen

data class CgTypePointer(val target: CgType) : CgType {
    override val llvmType = "$target*"
    override fun toString() = llvmType
}
