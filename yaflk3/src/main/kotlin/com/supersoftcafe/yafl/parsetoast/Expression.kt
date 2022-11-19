package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.ast.*
import org.antlr.v4.runtime.ParserRuleContext
import org.antlr.v4.runtime.Token
import org.antlr.v4.runtime.tree.TerminalNode



private fun YaflParser.BuiltinExprContext.toBuiltinExpression(
    file: String
): Expression {
    fun build(builder: (SourceRef, TypeRef, Expression, Expression) -> Expression, typeRef: TypeRef): Expression {
        val params = params.exprOfTuplePart().map { it.expression().toExpression(file) }
        if (params.size != 2)
            throw IllegalArgumentException("Param count must be 2")
        return builder(toSourceRef(file), typeRef, params[0], params[1])
    }
    return when (val name = NAME().text) {
        "add_i32" -> build(Expression::Add, TypeRef.Primitive(PrimitiveKind.Int32))
        "add_i64" -> build(Expression::Add, TypeRef.Primitive(PrimitiveKind.Int64))
        else -> throw IllegalArgumentException("Unrecognised builtin $name")
    }
}

private fun YaflParser.ExprOfTupleContext.toTupleExpression(
    file: String
): Expression {
    val result = Expression.Tuple(toSourceRef(file), null, exprOfTuplePart().map {
        TupleExpressionField(it.expression().toExpression(file), it.unpack != null, it.NAME()?.text)
    })

    if (result.fields.size == 1 && result.fields[0].name == null && !result.fields[0].unpack) {
        return result.fields[0].expression
    } else {
        return result
    }
}

private fun YaflParser.ApplyExprContext.toApplyExpression(
    file: String
): Expression {
    val left = left.toExpression(file)
    val right = right.toExpression(file)

    return if (PIPE_RIGHT() != null) {
        if (right is Expression.Call) {
            right.copy(
                parameter = Expression.Tuple(
                    toSourceRef(file),
                    null,
                    listOf(
                        TupleExpressionField(right.parameter, true, null),
                        TupleExpressionField(left, true, null)
                    )
                )
            )
        } else {
            throw IllegalArgumentException()
        }
    } else if (PIPE_MAYBE() != null) {
        TODO()
    } else {
        throw IllegalArgumentException()
    }
}

private fun YaflParser.IntegerExprContext.toIntegerExpression(
    file: String
): Expression {
    fun String.parse(type: PrimitiveKind, sign: Boolean, radix: Int) =
        Expression.Integer(toSourceRef(file), TypeRef.Primitive(type), toLong(radix) * (if (sign) -1 else 1))

    fun String.parse(type: PrimitiveKind, sign: Boolean) = when (take(2)) {
        "0b" -> drop(2).parse(type, sign, 2)
        "0o" -> drop(2).parse(type, sign, 8)
        "0x" -> drop(2).parse(type, sign, 16)
        else -> parse(type, sign, 10)
    }

    fun String.parse(type: PrimitiveKind) = when (take(1)) {
        "-" -> drop(1).parse(type, true)
        "+" -> drop(1).parse(type, false)
        else -> parse(type, false)
    }

    fun String.parse() = when {
        endsWith("i8") -> dropLast(2).parse(PrimitiveKind.Int8)
        endsWith("i16") -> dropLast(3).parse(PrimitiveKind.Int16)
        endsWith("i32") -> dropLast(3).parse(PrimitiveKind.Int32)
        endsWith("i64") -> dropLast(3).parse(PrimitiveKind.Int64)
        endsWith("s") || endsWith("S") -> dropLast(1).parse(PrimitiveKind.Int16)
        endsWith("l") || endsWith("L") -> dropLast(1).parse(PrimitiveKind.Int64)
        else -> parse(PrimitiveKind.Int32)
    }

    return text.parse()
}

private fun YaflParser.ExpressionContext.toBinaryOperator(
    file: String,
    left: YaflParser.ExpressionContext,
    operator: Token,
    right: YaflParser.ExpressionContext
): Expression {
    val sourceRef = toSourceRef(file)
    return Expression.Call(
        sourceRef,
        null,
        Expression.LoadData(
            sourceRef,
            null,
            DataRef.Unresolved("`${operator.text}`")),
        Expression.Tuple(
            sourceRef,
            null,
            listOf(
                TupleExpressionField(left.toExpression(file), false, null),
                TupleExpressionField(right.toExpression(file), false, null)
            )
        )
    )
}

private fun YaflParser.CallExprContext.toCallExpression(
    file: String
): Expression {
    val left = left.toExpression(file)
    val params = params.toTupleExpression(file)

    return Expression.Call(
        toSourceRef(file), null, left,
        if (params is Expression.Tuple) params else Expression.Tuple(
            params.sourceRef,
            TypeRef.Tuple(listOf(TupleTypeField(params.typeRef, null))),
            listOf(TupleExpressionField(params, false, null))
        )
    )
}

fun YaflParser.ExpressionContext.toExpression(
    file: String
): Expression {
    return when (this) {
        is YaflParser.NameExprContext -> Expression.LoadData(toSourceRef(file), null, DataRef.Unresolved(qualifiedName().toName()))
        is YaflParser.DotExprContext -> Expression.LoadMember(toSourceRef(file), null, left.toExpression(file), right.text)

        is YaflParser.BuiltinExprContext -> toBuiltinExpression(file)
        is YaflParser.CallExprContext -> toCallExpression(file)
        is YaflParser.ApplyExprContext -> toApplyExpression(file)
        is YaflParser.ProductExprContext -> toBinaryOperator(file, left, operator, right)
        is YaflParser.SumExprContext -> toBinaryOperator(file, left, operator, right)
        is YaflParser.CompareExprContext -> toBinaryOperator(file, left, operator, right)
        is YaflParser.IfExprContext -> Expression.If(toSourceRef(file), null, condition.toExpression(file), left.toExpression(file), right.toExpression(file))

        is YaflParser.TupleExprContext -> exprOfTuple().toTupleExpression(file)
        is YaflParser.ObjectExprContext -> TODO()
        // is YaflParser.LetExprContext -> Expression.Let(null, letWithExpr().toDeclaration(id, isGlobal = false), expression().toExpression())
        // is YaflParser.FunctionExprContext -> Expression.Function(null, function().toDeclaration(id, isGlobal = false), expression().toExpression())

        is YaflParser.LambdaExprContext -> TODO()
        is YaflParser.StringExprContext -> TODO()
        is YaflParser.IntegerExprContext -> toIntegerExpression(file)


        else -> TODO()
    }
}
