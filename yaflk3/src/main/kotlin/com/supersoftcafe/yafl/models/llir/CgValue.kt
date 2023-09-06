package com.supersoftcafe.yafl.models.llir

import com.supersoftcafe.yafl.utils.Namer

sealed class CgValue {
    abstract val type: CgType
    open fun updateRegisters(registerMap: (String) -> String) = this

    data class Global(val name: String, override val type: CgType) : CgValue() {
        override fun toString() = "@\"$name\""
    }
    data class Register(val name: String, override val type: CgType) : CgValue() {
        constructor(name: Namer, type: CgType): this(name.toString(), type)
        override fun toString() = if (name.isEmpty()) name else "%\"$name\""
        override fun updateRegisters(registerMap: (String) -> String) = Register(registerMap(name), type)
    }
    data class Immediate(val value: String, override val type: CgType) : CgValue() {
        override fun toString() = value
    }

    companion object {
        val NULL = Immediate("null", CgTypePrimitive.OBJECT)
        val THIS = Register("this", CgTypePrimitive.OBJECT)
        val VOID = Register("", CgTypePrimitive.VOID)
        val UNIT = Global("global_unit", CgTypePrimitive.OBJECT)
        val ZERO = Immediate("0", CgTypePrimitive.INT32)
        val ONE = Immediate("1", CgTypePrimitive.INT32)
        val FALSE = Immediate("0", CgTypePrimitive.BOOL)
        val TRUE = Immediate("1", CgTypePrimitive.BOOL)

        fun undef(type: CgType): CgValue = Immediate("undef", type)
    }
}
