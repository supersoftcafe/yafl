package com.supersoftcafe.yaflc.codegen

data class CgThingFunction(
    val name: String,
    val result: CgType,
    val params: List<CgThingVariable>,
    val variables: List<CgThingVariable>,
    val body: List<CgOp>
) : CgThing, Iterable<CgOp> {
    constructor(name: String, result: CgType, param1: CgThingVariable, vararg body: CgOp) : this(name, result, listOf(param1), listOf(), body.toList())
    constructor(name: String, result: CgType, param1: CgThingVariable, param2: CgThingVariable, vararg body: CgOp) : this(name, result, listOf(param1, param2), listOf(), body.toList())
    constructor(name: String, result: CgType, params: List<CgThingVariable>, vararg body: CgOp) : this(name, result, params, listOf(), body.toList())

    init {
        if (params.firstOrNull()?.type != CgTypePrimitive.OBJECT)
            throw IllegalArgumentException("First parameter must be OBJECT")
    }

    override fun iterator() = body.iterator()

    fun toIr(context: CgContext): CgLlvmIr {
        val paramTypeStr = params.joinToString { "${it.type}" }
        val paramVarStr = params.joinToString { "${it.type} ${it.name}" }
        val lines = variables.map { "  ${it.name} = alloca ${it.type}\n" } + body.map { it.toIr(context) }
        return CgLlvmIr(
            types = "%typeof.$name = type $result($paramTypeStr)\n",
            declarations = lines.joinToString("", "define internal tailcc $result @$name ($paramVarStr) {\n", "}\n\n"))
    }

    fun addPreamble(preamble: List<CgOp>): CgThingFunction {
        val first = body.firstOrNull()
        return copy(body = if (first is CgOp.Label) {
            preamble + CgOp.Jump(first.name) + body
        } else {
            preamble + body
        })
    }

    companion object {
        fun nothing(name: String) = CgThingFunction(name,
            CgTypePrimitive.VOID,
            CgThingVariable.THIS,
            CgOp.Label("start"),
            CgOp.Return(CgTypePrimitive.VOID, ""))

        fun main(vararg body: CgOp) =
            CgThingFunction("synth_main", CgTypePrimitive.INT32, CgThingVariable.THIS, *body)
    }
}
