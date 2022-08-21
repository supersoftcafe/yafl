package com.supersoftcafe.yaflc.codegen

class CgThingVariable(val name: String, val type: CgType) : CgThing {
    fun toIr(context: CgContext): CgLlvmIr {
        return CgLlvmIr(declarations = "@${name.escape()} = internal global $type zeroinitializer\n")
    }

    companion object {
        val THIS = CgThingVariable("%this", CgTypePrimitive.OBJECT)
    }
}
