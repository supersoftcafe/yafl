package com.supersoftcafe.yaflc.codegen

sealed class CgValue {
    abstract val type: CgType
    open fun updateRegisters(registerMap: (String) -> String) = this

    data class Global(val name: String, override val type: CgType) : CgValue() {
        override fun toString() = "@${name.llEscape()}"
    }
    data class Register(val name: String, override val type: CgType) : CgValue() {
        override fun toString() = "%${name.llEscape()}"
        override fun updateRegisters(registerMap: (String) -> String) = Register(registerMap(name), type)
    }
    data class Immediate(val value: String, override val type: CgType) : CgValue() {
        override fun toString() = value
    }

    companion object {
        val NULL = CgValue.Immediate("null", CgTypePrimitive.OBJECT)
        val THIS = CgValue.Register("%this", CgTypePrimitive.OBJECT)
        val VOID = CgValue.Register("", CgTypePrimitive.VOID)
    }
}
