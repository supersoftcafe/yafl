package com.supersoftcafe.yaflc.codegen

data class CgTypeStruct(val fields: List<CgType>) : CgType {
    override val llvmType = "{${fields.joinToString { it.llvmType }}}"
    override fun toString() = llvmType
}
