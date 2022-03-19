package yafl.ast

import java.math.BigInteger

private fun tupleTypeToAstTuple(tuple: yaflParser.TupleTypeContext) = Type.Tuple(
    tuple.parameter().map { DeclareField(it.NAME().text, it.type()?.let { typeToAstType(it) }) }
)

private fun typeToAstType(type: yaflParser.TypeContext): Type {
    val namedType = type.namedType()
    val tupleType = type.tupleType()

    return if (namedType != null) {
        if (namedType.genericParams() != null)
            throw IllegalArgumentException("Generics not implemented yet")
        Type.Named(namedType.simpleTypeName().text, listOf())
    } else if (tupleType != null) {
        throw IllegalArgumentException("Tuple not supported yet")
    } else {
        throw IllegalArgumentException("Unknown type from antlr")
    }
}

private fun integerExpressionToNumber(expression: yaflParser.IntegerExpressionContext): Expression.Number {
    val fullString = expression.text.replace("_", "")
    val withoutSign = fullString.removePrefix("-")
    val indexOfI = withoutSign.lastIndexOfAny(charArrayOf('s', 'S', 'i', 'I', 'l', 'L'))
    val withoutType = if (indexOfI >= 0) withoutSign.take(indexOfI) else withoutSign
    val typeSuffix = if (indexOfI >= 0) withoutSign.drop(indexOfI) else "i"

    val number = when (withoutType.take(2)) {
        "0x" -> BigInteger(withoutType.drop(2), 16)
        "0o" -> BigInteger(withoutType.drop(2),  8)
        "0b" -> BigInteger(withoutType.drop(2),  2)
        else -> BigInteger(withoutType        , 10)
    }.let { if (fullString.first() == '-') it.inv() else it }

    return when (typeSuffix) {
        "i8" -> Expression.Number.Int8(number.toByte())
        "s", "S", "i16" -> Expression.Number.Int16(number.toShort())
        "i", "I", "i32" -> Expression.Number.Int32(number.toInt())
        "l", "L", "i64" -> Expression.Number.Int64(number.toLong())
        else -> throw IllegalArgumentException()
    }
}

private fun expressionToAstExpression(expression: yaflParser.ExpressionContext): Expression {
    return when (expression) {
        is yaflParser.DotExpressionContext ->
            throw IllegalArgumentException("Dot expressions not implemented")
            // Expression.Operator.Dot(expressionToAstExpression(expression.expression()), expression.NAME().text)

        is yaflParser.IntegerExpressionContext ->
            integerExpressionToNumber(expression)

        is yaflParser.NamedValueExpressionContext ->
            Expression.Operator.NamedThing(expression.NAME().text)

        else -> throw IllegalArgumentException()
    }
}

private fun funToAstFun(
    module: String, imports: List<String>,
    function: yaflParser.FunContext
) = Declaration.Fun(
    function.NAME().text, module, imports,
    function.tupleType()?.let { tupleTypeToAstTuple(it) } ?: Type.Tuple(listOf()),
    function.type()?.let { typeToAstType(it) },
    function.statements().map { statementToAstDeclaration(module, imports, it) },
    expressionToAstExpression(function.expression())
)

private fun statementToAstDeclaration(
    module: String, imports: List<String>,
    statement: yaflParser.StatementsContext
): Declaration {
    return when {
        statement.`fun`() != null -> funToAstFun(module, imports, statement.`fun`())
        else -> throw IllegalArgumentException()
    }
}

private fun declarationToAstDeclaration(
    module: String, imports: List<String>,
    declaration: yaflParser.DeclarationsContext
): Declaration {
    return when {
        declaration.`fun`() != null -> funToAstFun(module, imports, declaration.`fun`())
        else -> throw IllegalArgumentException()
    }
}

fun parseTreesToAstProject(files: List<yaflParser.RootContext>) = AstProject(
    files.flatMap { file ->
        file.modules().flatMap { section ->
            val module = section.module().text
            val imports = section.imports().map { import -> import.simpleTypeName().text }
            section.declarations().map { declaration -> declarationToAstDeclaration(module, imports, declaration) }
        }
    }.groupBy { it.module }
)

