package com.supersoftcafe.yaflc.codegen

class CgThingVariable(val name: String, val type: CgType) : CgThing {
    companion object {
        val THIS = CgThingVariable("%this", CgTypePrimitive.OBJECT)
    }
}
