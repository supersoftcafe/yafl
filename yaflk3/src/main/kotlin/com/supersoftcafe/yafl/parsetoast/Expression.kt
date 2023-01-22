package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Namer
import org.antlr.v4.runtime.Token
import org.antlr.v4.runtime.tree.TerminalNode




private fun YaflParser.AssertExprContext.toAssertExpression(
    file: String,
    namer: Namer,
): Expression {
    return Expression.Assert(
        toSourceRef(file),
        null,
        value.toExpression(file, namer+1),
        condition.toExpression(file, namer+2),
        message.text.removeSurrounding("\""))
}

private fun YaflParser.LlvmirExprContext.toLlvmirExpression(
    file: String,
    namer: Namer,
): Expression {
    return Expression.Llvmir(
        toSourceRef(file),
        type().toTypeRef(),
        pattern.text.removeSurrounding("\""),
        expression().map { it.toExpression(file, namer) })
}

private fun YaflParser.ExprOfTupleContext.toTupleExpression(
    file: String,
    namer: Namer,
): Expression {
    val result = Expression.Tuple(toSourceRef(file), null, exprOfTuplePart().map {
        TupleExpressionField(it.NAME()?.text, it.expression().toExpression(file, namer))
    })

    if (result.fields.size == 1 && result.fields[0].name == null) {
        return result.fields[0].expression
    } else {
        return result
    }
}

private fun YaflParser.ApplyExprContext.toApplyExpression(
    file: String,
    namer: Namer,
): Expression {
    TODO()
}

fun TerminalNode.parseToInteger(
    sourceRef: SourceRef
): Expression.Integer {
    fun String.parse(type: PrimitiveKind, radix: Int) =
        Expression.Integer(sourceRef, TypeRef.Primitive(type), toLong(radix))

    fun String.parse(type: PrimitiveKind) = when (take(2)) {
        "0b" -> drop(2).parse(type, 2)
        "0o" -> drop(2).parse(type, 8)
        "0x" -> drop(2).parse(type, 16)
        else -> parse(type, 10)
    }

    fun String.parse() = when {
        endsWith("i8") -> dropLast(2).parse(com.supersoftcafe.yafl.ast.PrimitiveKind.Int8)
        endsWith("i16") -> dropLast(3).parse(com.supersoftcafe.yafl.ast.PrimitiveKind.Int16)
        endsWith("i32") -> dropLast(3).parse(com.supersoftcafe.yafl.ast.PrimitiveKind.Int32)
        endsWith("i64") -> dropLast(3).parse(com.supersoftcafe.yafl.ast.PrimitiveKind.Int64)
        endsWith("s") || endsWith("S") -> dropLast(1).parse(com.supersoftcafe.yafl.ast.PrimitiveKind.Int16)
        endsWith("l") || endsWith("L") -> dropLast(1).parse(com.supersoftcafe.yafl.ast.PrimitiveKind.Int64)
        else -> parse(com.supersoftcafe.yafl.ast.PrimitiveKind.Int32)
    }

    return text.parse()
}

private fun YaflParser.IntegerExprContext.toIntegerExpression(
    file: String
): Expression.Integer {
    return INTEGER().parseToInteger(toSourceRef(file))
}

private fun call(sourceRef: SourceRef, name: String, vararg params: Expression): Expression.Call {
    return Expression.Call(
        sourceRef,
        null,
        Expression.LoadData(sourceRef, null, DataRef.Unresolved(name)),
        Expression.Tuple(sourceRef, null, params.map { TupleExpressionField(null, it) })
    )
}

private fun YaflParser.ExpressionContext.toUnaryOperator(
    file: String,
    namer: Namer,
    operator: Token,
    right: YaflParser.ExpressionContext
): Expression {
    return call(toSourceRef(file), "`${operator.text}`", right.toExpression(file, namer))
}

private fun YaflParser.ExpressionContext.toBinaryOperator(
    file: String,
    namer: Namer,
    left: YaflParser.ExpressionContext,
    operator: Token,
    right: YaflParser.ExpressionContext
): Expression {
    return call(toSourceRef(file), "`${operator.text}`", left.toExpression(file, namer + 1), right.toExpression(file, namer + 2))
}

private fun YaflParser.CallExprContext.toCallExpression(
    file: String,
    namer: Namer,
): Expression {
    val left = left.toExpression(file, namer + 1)
    val params = params.toTupleExpression(file, namer + 2)

    return Expression.Call(
        toSourceRef(file), null, left,
        if (params is Expression.Tuple) params else Expression.Tuple(
            params.sourceRef,
            TypeRef.Tuple(listOf(TupleTypeField(params.typeRef, null))),
            listOf(TupleExpressionField(null, params))
        )
    )
}

fun YaflParser.ExpressionContext.toExpression(
    file: String,
    namer: Namer,
): Expression {
    return when (this) {
        is YaflParser.AssertExprContext -> toAssertExpression(file, namer)

        is YaflParser.ArrayLookupExprContext -> Expression.ArrayLookup(toSourceRef(file), null, left.toExpression(file, namer + 1), right.toExpression(file, namer + 2))

        is YaflParser.NameExprContext -> Expression.LoadData(toSourceRef(file), null, DataRef.Unresolved(qualifiedName().toName()))
        is YaflParser.DotExprContext -> Expression.LoadMember(toSourceRef(file), null, left.toExpression(file, namer), right.text)

        is YaflParser.LlvmirExprContext -> toLlvmirExpression(file, namer)
        is YaflParser.CallExprContext -> toCallExpression(file, namer)
        is YaflParser.ApplyExprContext -> toApplyExpression(file, namer)

        is YaflParser.UnaryExprContext -> toUnaryOperator(file, namer, operator, right)
        is YaflParser.ProductExprContext -> toBinaryOperator(file, namer, left, operator, right)
        is YaflParser.SumExprContext -> toBinaryOperator(file, namer, left, operator, right)
        is YaflParser.ShiftExprContext -> toBinaryOperator(file, namer, left, operator, right)
        is YaflParser.CompareExprContext -> toBinaryOperator(file, namer, left, operator, right)
        is YaflParser.EqualExprContext -> toBinaryOperator(file, namer, left, operator, right)
        is YaflParser.BitAndExprContext -> toBinaryOperator(file, namer, left, operator, right)
        is YaflParser.BitXorExprContext -> toBinaryOperator(file, namer, left, operator, right)
        is YaflParser.BitOrExprContext -> toBinaryOperator(file, namer, left, operator, right)

        is YaflParser.IfExprContext -> Expression.If(toSourceRef(file), null, condition.toExpression(file, namer + 1), left.toExpression(file, namer + 2), right.toExpression(file, namer + 3))

        is YaflParser.TupleExprContext -> exprOfTuple().toTupleExpression(file, namer)
        is YaflParser.ObjectExprContext -> TODO()
        is YaflParser.LetExprContext -> Expression.Let(toSourceRef(file), null, letWithExpr().toDeclaration(file, namer + 1, Scope.Local), expression().toExpression(file, namer + 2))
        // is YaflParser.FunctionExprContext -> Expression.Function(null, function().toDeclaration(id, isGlobal = false), expression().toExpression())

        is YaflParser.LambdaExprContext -> Expression.Lambda(toSourceRef(file), null, unpackTuple().toDeclarationLets(file, namer+1, Scope.Local), expression().toExpression(file, namer+2), namer+3)

        is YaflParser.StringExprContext -> Expression.Characters(toSourceRef(file), TypeRef.Unresolved("System::String", null), text.removeSurrounding("\""))
        is YaflParser.IntegerExprContext -> toIntegerExpression(file)


        else -> TODO()
    }
}
