package yafl.ast

import java.math.BigDecimal
import java.math.BigInteger

data class AstProject(val files: List<File>)
data class File(val module: String?, val imports: List<String>, val declarations: List<Declaration>)
data class Field(val name: String, val type: Type?)

sealed class Declaration {
    abstract val name: String

    data class Var(override val name: String, val type: Type, val expression: Expression) : Declaration()

    data class Fun(
        override val name: String,
        val params: Type.Tuple,
        val type: Type?,
        val declarations: List<Declaration>,
        val expression: Expression?
    ) : Declaration()

    data class Object(override val name: String, val declarations: List<Declaration>) : Declaration()
    data class Struct(override val name: String, val declarations: List<Declaration>) : Declaration()

    data class Trait(override val name: String, val declarations: List<Declaration>) : Declaration()
    data class Implement(override val name: String, val declarations: List<Declaration>) : Declaration()
}

sealed class Type {
    data class Tuple(val fields: List<Field>) : Type()
    data class Named(val name: String, val genericParams: List<Type>) : Type()
}

sealed class Expression {
    sealed class Number : Expression() {
        data class Int8(val value: Byte) : Number()
        data class Int16(val value: Short) : Number()
        data class Int32(val value: Int) : Number()
        data class Int64(val value: Long) : Number()
        data class Float32(val value: Float) : Number()
        data class Float64(val value: Double) : Number()
    }
    sealed class Operator : Expression() {
        data class Plus(val left: Expression, val right: Expression) : Operator()
        data class Divide(val left: Expression, val right: Expression) : Operator()
        data class Multiple(val left: Expression, val right: Expression) : Operator()
        data class Remainder(val left: Expression, val right: Expression) : Operator()
        data class Minus(val left: Expression, val right: Expression) : Operator()
        data class UnaryMinus(val value: Expression) : Operator()
    }
}


private fun tupleTypeToAstTuple(tuple: yaflParser.TupleTypeContext) = Type.Tuple(
    tuple.parameter().map { Field(it.NAME().text, it.type()?.let { typeToAstType(it) }) }
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

private fun expressionToAstExpression(expression: yaflParser.ExpressionContext): Expression {
    return when (expression) {
        is yaflParser.IntegerExpressionContext -> {
            val fullString = expression.text.replace("_", "")
            val withoutSign = fullString.removePrefix("-")
            val indexOfI = withoutSign.lastIndexOfAny(charArrayOf('s', 'S', 'i', 'I', 'l', 'L'))
            val withoutType = if (indexOfI >= 0) withoutSign.take(indexOfI) else withoutSign
            val typeSuffix = if (indexOfI >= 0) withoutSign.drop(indexOfI) else "i"

            val number = when (withoutType.take(2)) {
                "0x" -> BigInteger(withoutType.drop(2), 16)
                "0o" -> BigInteger(withoutType.drop(2), 8)
                "0b" -> BigInteger(withoutType.drop(2), 2)
                else -> BigInteger(withoutType        , 10)
            }.let { if (fullString.first() == '-') it.inv() else it }

            when (typeSuffix) {
                "i8" -> Expression.Number.Int8(number.toByte())
                "s", "S", "i16" -> Expression.Number.Int16(number.toShort())
                "i", "I", "i32" -> Expression.Number.Int32(number.toInt())
                "l", "L", "i64" -> Expression.Number.Int64(number.toLong())
                else -> throw IllegalArgumentException()
            }
        }
        else -> throw IllegalArgumentException()
    }
}

private fun funToAstFun(function: yaflParser.FunContext) = Declaration.Fun(
    function.NAME().text,
    function.tupleType()?.let { tupleTypeToAstTuple(it) } ?: Type.Tuple(listOf()),
    function.type()?.let { typeToAstType(it) },
    function.statements().map { statementToAstDeclaration(it) },
    expressionToAstExpression(function.expression())
)

private fun statementToAstDeclaration(statement: yaflParser.StatementsContext): Declaration {
    return when {
        statement.`fun`() != null -> funToAstFun(statement.`fun`())
        else -> throw IllegalArgumentException()
    }
}

private fun declarationToAstDeclaration(declaration: yaflParser.DeclarationsContext): Declaration {
    return when {
        declaration.`fun`() != null -> funToAstFun(declaration.`fun`())
        else -> throw IllegalArgumentException()
    }
}

fun parseTreeToAstFile(root: yaflParser.RootContext) = File(
    root.module()?.simpleTypeName()?.text,
    root.imports().map { it.simpleTypeName().text },
    root.declarations().map { declarationToAstDeclaration(it) }
)



