package com.supersoftcafe.yaflc.codegen

sealed class CgValue {
    open fun updateRegisters(registerMap: (String) -> String) = this

    data class Global(val name: String) : CgValue() {
        override fun toString() = "@${name.escape()}"
    }
    data class Register(val name: String) : CgValue() {
        override fun toString() = "%${name.escape()}"
        override fun updateRegisters(registerMap: (String) -> String) = Register(registerMap(name))
    }
    data class Immediate(val value: String) : CgValue() {
        override fun toString() = value
    }
}
