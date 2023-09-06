package com.supersoftcafe.yafl.models.llir

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


    override fun toIr(context: CgContext): CgLlvmIr {
        val paramTypeStr = params.joinToString { "${it.type}" }
        val paramVarStr = params.joinToString { "${it.type} %\"${it.name}\"" }
        val functionTypeName = CgValue.Register("typeof.$globalName", CgTypePrimitive.VOID)

        val paramsSansThis = params.drop(1)

        val externDecl = paramsSansThis.joinToString(", ", "declare dso_local noundef $resultType @\"$externName\"(", ") local_unnamed_addr\n") {
            it.type.toString() + " noundef" + if (it.type is CgTypePointer || (it.type is CgTypePrimitive && it.type.subType == CgSubType.POINTER))
                " readonly nocapture" else ""
        }
        val globalDecl = "define internal $resultType @\"$globalName\"($paramVarStr) {\n"
        val callOp = paramsSansThis.joinToString(", ", "  %result = call $resultType @\"$externName\"(", ")\n") { "${it.type} $it" }
        val retOp = "  ret $resultType %result\n"

        return CgLlvmIr(
            types = "$functionTypeName = type $resultType($paramTypeStr)\n",
            declarations = "$externDecl$globalDecl$callOp$retOp}\n\n"
        )
    }

}
