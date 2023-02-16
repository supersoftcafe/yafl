package com.supersoftcafe.yafl.codegen

class CgThingStruct(
    val name: String,
    val type: CgTypeStruct
) : CgThing {

    override fun toIr(context: CgContext): CgLlvmIr {
        return CgLlvmIr(types = "%struct.$name = type $type\n")
    }
}