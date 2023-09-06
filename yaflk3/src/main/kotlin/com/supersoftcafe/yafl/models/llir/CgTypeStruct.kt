package com.supersoftcafe.yafl.models.llir

data class CgTypeStruct(val fields: List<CgType>) : CgType {
    override val llvmType = "{${fields.joinToString { it.llvmType }}}"
    override fun toString() = llvmType

    companion object {
        val functionPointer = CgTypeStruct(listOf(CgTypePrimitive.FUNPTR, CgTypePrimitive.OBJECT))
    }
}
