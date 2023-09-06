package com.supersoftcafe.yafl.models.llir

data class CgTypePointer(val target: CgType) : CgType {
    override val llvmType = "ptr"
    override fun toString() = llvmType
}
