package com.supersoftcafe.yafl.codegen

data class CgTypePointer(val target: CgType) : CgType {
    override val llvmType = "ptr"
    override fun toString() = llvmType
}
