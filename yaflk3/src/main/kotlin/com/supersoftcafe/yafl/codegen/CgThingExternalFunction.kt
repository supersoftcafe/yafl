package com.supersoftcafe.yafl.codegen

data class CgThingExternalFunction(
    val globalName: String,     // A globally unique name that can be used to refer to the function definition
    val externName: String,     // The c-library function name
    val resultType: CgType,
    val params: List<CgValue.Register>,
) : CgThing {

    init {
        if (params.firstOrNull()?.type != CgTypePrimitive.OBJECT)
            throw IllegalArgumentException("First parameter must be OBJECT")
    }


    fun toIr(context: CgContext): CgLlvmIr {
        val paramTypeStr = params.joinToString { "${it.type}" }
        val paramVarStr = params.joinToString { "${it.type} %\"${it.name}\"" }
        val functionTypeName = CgValue.Register("typeof.$globalName", CgTypePrimitive.VOID)

        val paramsSansThis = params.drop(1)

        val externDecl = paramsSansThis.joinToString(", ", "declare dso_local $resultType @\"$externName\"(", ")\n") { it.type.toString() }
        val globalDecl = "define internal tailcc $resultType @\"$globalName\"($paramVarStr) {\n"
        val callOp = paramsSansThis.joinToString(", ", "  %result = call $resultType @\"$externName\"(", ")\n") { "${it.type} $it" }
        val retOp = "  ret $resultType %result\n"

        return CgLlvmIr(
            types = "$functionTypeName = type $resultType($paramTypeStr)\n",
            declarations = "$externDecl$globalDecl$callOp$retOp}\n\n"
        )
    }

}
