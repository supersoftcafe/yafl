package com.supersoftcafe.yafl.codegen

class CgThingVariable(
    val name: String,
    val type: CgType
) : CgThing {

    // Only if this is a global var. As a local this function should not be used.
    override fun toIr(context: CgContext): CgLlvmIr {
        return CgLlvmIr(declarations = "@\"$name\" = internal global $type zeroinitializer\n")
    }

    // Only if this is a local var. As a global this function has no meaning.
    fun toValue(): CgValue {
        return CgValue.Register(name, type)
    }
}
