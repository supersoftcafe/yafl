package com.supersoftcafe.yafl.codegen

class CgTypeArray(val type: CgType, val size: Int) : CgType {

    override val llvmType = "[$size x $type]"
    override fun toString() = llvmType
}