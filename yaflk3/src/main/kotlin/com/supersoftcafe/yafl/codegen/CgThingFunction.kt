package com.supersoftcafe.yafl.codegen


data class CgThingFunction(
    val globalName: String,     // A globally unique name that can be used to refer to the function definition
    val nameOfSlot: String,     // A signature that multiple functions can share if they are effectively equivalent
    val resultType: CgType,
    val params: List<CgValue.Register>,
    val body: List<CgOp>
) : CgThing, Iterable<CgOp> {
    constructor(globalName: String, nameOfSlot: String, result: CgType, param1: CgValue.Register, vararg body: CgOp) : this(globalName, nameOfSlot, result, listOf(param1), body.toList())
    constructor(globalName: String, nameOfSlot: String, result: CgType, param1: CgValue.Register, param2: CgValue.Register, vararg body: CgOp) : this(globalName, nameOfSlot, result, listOf(param1, param2), body.toList())
    constructor(globalName: String, nameOfSlot: String, result: CgType, params: List<CgValue.Register>, vararg body: CgOp) : this(globalName, nameOfSlot, result, params, body.toList())

    init {
        if (params.firstOrNull()?.type != CgTypePrimitive.OBJECT)
            throw IllegalArgumentException("First parameter must be OBJECT")
    }

    override fun iterator() = body.iterator()

    override fun toIr(context: CgContext): CgLlvmIr {
        val lines = body.map { it.toIr(context) }
        val paramTypeStr = params.joinToString { "${it.type}" }
        val paramVarStr = params.joinToString { "${it.type} %\"${it.name}\"" }
        val functionTypeName = CgValue.Register("typeof.$globalName", CgTypePrimitive.VOID)
        val idPrefix = context.slotNameToId(nameOfSlot)?.let { "prefix %size_t $it " } ?: ""
        return CgLlvmIr(
            types = "$functionTypeName = type $resultType($paramTypeStr)\n",
            declarations = lines.joinToString("", "define internal $resultType @\"$globalName\"($paramVarStr) $idPrefix{\n", "}\n\n"))
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
        fun nothing(name: String, signature: String) = CgThingFunction(
            name,
            signature,
            CgTypePrimitive.VOID,
            CgValue.THIS,
            CgOp.Label("start"),
            CgOp.Return(CgValue.Immediate("", CgTypePrimitive.VOID)))

        fun main(vararg body: CgOp) =
            CgThingFunction("synth_main", "synth_main", CgTypePrimitive.INT32, CgValue.THIS, *body)
    }
}
