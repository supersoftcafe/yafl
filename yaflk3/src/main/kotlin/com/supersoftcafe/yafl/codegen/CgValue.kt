package com.supersoftcafe.yafl.codegen

sealed class CgValue {
    abstract val type: CgType
    open fun updateRegisters(registerMap: (String) -> String) = this

    data class Global(val name: String, override val type: CgType) : CgValue() {
        override fun toString() = "@\"$name\""
    }
    data class Register(val name: String, override val type: CgType) : CgValue() {
        override fun toString() = "%\"$name\""
        override fun updateRegisters(registerMap: (String) -> String) = Register(registerMap(name), type)
    }
    data class Immediate(val value: String, override val type: CgType) : CgValue() {
        override fun toString() = value
    }

    companion object {
        val NULL = CgValue.Immediate("null", CgTypePrimitive.OBJECT)
        val THIS = CgValue.Register("this", CgTypePrimitive.OBJECT)
        val VOID = CgValue.Register("", CgTypePrimitive.VOID)
        val UNIT = CgValue.Global("global_unit", CgTypePrimitive.OBJECT)

        fun undef(type: CgType): CgValue = CgValue.Immediate("undef", type)
    }
}
