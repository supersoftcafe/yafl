package yafl.ir



fun astTypeToIrType(type: yafl.ast.Type): Type {
    return when (type) {
        is yafl.ast.Type.Tuple -> Type.Struct(type.fields.map { astTypeToIrType(it.type!!) })
        is yafl.ast.Type.Named -> when (type.name) {
            "System.Int8" -> Type.Int8
            "System.Int16" -> Type.Int16
            "System.Int32" -> Type.Int32
            "System.Int64" -> Type.Int64
            else -> throw IllegalArgumentException()
        }
    }
}

fun astExpressionToIrCodeBlocks(expression: yafl.ast.Expression, target: String): List<CodeBlock> {
    return when (expression) {
        is yafl.ast.Expression.Number.Int32 -> listOf(CodeBlock(target + '0', listOf(
            Op.LoadC(Field(target, Type.Int32), expression.value),
            Op.Jump(target)
        )))
        is yafl.ast.Expression.Memory.LoadGlobal -> listOf(CodeBlock(target + '0', listOf(
            ,
            Op.Jump(target)
        )))
        else -> throw IllegalArgumentException()
    }
}

fun astFunToIrFun(function: yafl.ast.Declaration.Fun): Function {
    if (function.declarations.isNotEmpty())
        throw IllegalArgumentException()
    val resultTarget = "rslt"
    return Function(
        function.module.replace('.', '_') + '_' + function.name,
        function.params.fields.map { Field(it.name, astTypeToIrType(it.type!!)) },
        astTypeToIrType(function.type!!),
        astExpressionToIrCodeBlocks(function.expression!!, resultTarget) + listOf(CodeBlock(resultTarget, listOf(
            Op.ReturnR(resultTarget)
        )))
    )
}

fun astToIr(ast: yafl.ast.AstProject) = Program(
    ast.modules.flatMap { module ->
        module.value.map { declaration ->
            when (declaration) {
                is yafl.ast.Declaration.Fun -> astFunToIrFun(declaration)
                else -> throw IllegalArgumentException()
            }
        }
    }
)
