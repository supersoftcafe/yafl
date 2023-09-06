package com.supersoftcafe.yafl.models.llir

data class CgOps(
    val ops: List<CgOp>,
    val result: CgValue,
) {
    constructor(ops: List<CgOp>) : this(ops, CgValue.VOID)
    constructor(pair: Pair<List<CgOp>, CgValue>) : this(pair.first, pair.second)
    constructor(op: CgOp) : this(listOf(op), op.result)

    operator fun plus(other: CgOp) = CgOps(ops + other, other.result)
    operator fun plus(other: CgOps) = CgOps(ops + other.ops, other.result)
    operator fun plus(other: Pair<List<CgOp>, CgValue>) = CgOps(ops + other.first, other.second)

    val finalLabel: String?
        get() = (ops.lastOrNull { it is CgOp.Label } as? CgOp.Label)?.name
}

fun combineWithPhi(branches: List<CgOps>): CgOps {
    val type = branches[0].result.type
    val name = branches[0].finalLabel

    assert(branches.all { it.finalLabel != null })
    assert(branches.all { it.result.type == type })

    branches.map { it.finalLabel!! }

    val result = CgValue.Register("$name.r", type)
    val label = CgOp.Label("$name.l")
    val phi = CgOp.Phi(result, branches.map { it.result to it.finalLabel!! })

    return CgOps(branches.flatMap { it.ops + CgOp.Jump(label.name) } + label + phi, result)
}