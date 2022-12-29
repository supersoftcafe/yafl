package com.supersoftcafe.yafl.codegen

data class CgTypeStruct(val fields: List<CgType>) : CgType {
    override val llvmType = "{${fields.joinToString { it.llvmType }}}"
    override fun toString() = llvmType
}
