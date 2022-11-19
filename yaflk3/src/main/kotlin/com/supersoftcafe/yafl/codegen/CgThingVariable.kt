package com.supersoftcafe.yafl.codegen

class CgThingVariable(val name: String, val type: CgType) : CgThing {
    fun toIr(context: CgContext): CgLlvmIr {
        return CgLlvmIr(declarations = "@\"$name\" = internal global $type zeroinitializer\n")
    }
    fun toValue(): CgValue {
        return CgValue.Register(name, type)
    }
}
