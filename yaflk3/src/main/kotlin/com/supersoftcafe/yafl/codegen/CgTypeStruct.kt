package com.supersoftcafe.yafl.codegen

data class CgTypeStruct(val fields: List<CgType>) : CgType {
    override val llvmType = "{${fields.joinToString { it.llvmType }}}"
    override fun toString() = llvmType

    companion object {
        val functionPointer = CgTypeStruct(listOf(CgTypePrimitive.FUNPTR, CgTypePrimitive.OBJECT))
    }
}
