package com.supersoftcafe.yaflc.codegen

data class CgThingFunction(
    val name: String,
    val result: CgType,
    val params: List<CgThingVariable>,
    val body: List<CgCodeBlock>
) : CgThing, Iterable<CgOp> {
    constructor(name: String, result: CgType, param1: CgThingVariable, vararg body: CgCodeBlock) : this(name, result, listOf(param1), body.toList())
    constructor(name: String, result: CgType, param1: CgThingVariable, param2: CgThingVariable, vararg body: CgCodeBlock) : this(name, result, listOf(param1, param2), body.toList())
    constructor(name: String, result: CgType, params: List<CgThingVariable>, vararg body: CgCodeBlock) : this(name, result, params, body.toList())

    init {
        if (params.firstOrNull()?.type != CgTypePrimitive.OBJECT)
            throw IllegalArgumentException("First parameter must be OBJECT")
    }

    override fun iterator() = body.asSequence().flatMap { it.ops }.iterator()

    fun toIr(context: CgContext): CgLlvmIr {
        val paramTypeStr = params.joinToString { "${it.type}" }
        val paramVarStr = params.joinToString { "${it.type} ${it.name}" }
        return CgLlvmIr(
            types = "%typeof.$name = type $result($paramTypeStr)\n",
            declarations = body.joinToString("", "define internal tailcc $result @$name ($paramVarStr) {\n", "}\n\n") { it.toIr(context) })
    }

    companion object {
        fun nothing(name: String) = CgThingFunction(name,
            CgTypePrimitive.VOID,
            CgThingVariable.THIS,
            CgCodeBlock("start", CgOp.Return(CgTypePrimitive.VOID, "")))

        fun main(vararg body: CgCodeBlock) =
            CgThingFunction("synth_main", CgTypePrimitive.INT32, CgThingVariable.THIS, *body)
    }
}
