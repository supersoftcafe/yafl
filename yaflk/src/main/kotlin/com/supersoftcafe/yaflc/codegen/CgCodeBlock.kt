package com.supersoftcafe.yaflc.codegen

data class CgCodeBlock(val name: String, val ops: List<CgOp>) {
    constructor(name: String, vararg ops: CgOp) : this(name, ops.toList())

    fun toIr(context: CgContext): String {
        return ops.joinToString("", "$name:\n") { it.toIr(context) }
    }

    fun updateLabels(labelMap: (String) -> String): CgCodeBlock {
        return copy(name = labelMap(name), ops = ops.map { it.updateLabels(labelMap) })
    }

    fun updateRegisters(registerMap: (String) -> String): CgCodeBlock {
        return copy(ops = ops.map { it.updateRegisters(registerMap) })
    }
}
