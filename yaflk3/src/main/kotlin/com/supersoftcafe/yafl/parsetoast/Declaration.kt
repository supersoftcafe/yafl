package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.ast.*

//
//fun YaflParser.EnumContext.toDeclaration(id: Long, isGlobal: Boolean, prefix: String = ""): Pair<Declaration.Enum, Long> {
//    TODO()
//}
//
//fun YaflParser.ClassContext.toDeclaration(id: Long, isGlobal: Boolean, prefix: String = ""): Pair<Declaration.Klass, Long> {
//    TODO()
//}
//
//fun YaflParser.InterfaceContext.toDeclaration(id: Long, isGlobal: Boolean, prefix: String = ""): Pair<Declaration.Interface, Long> {
//    TODO()
//}

fun YaflParser.UnpackTupleContext.toDeclarationLets(file: String, id: Long): Pair<List<Declaration.Let>, Long> {
    return unpackTuplePart().fold(Pair(listOf<Declaration.Let>(), id)) { (list, id), part ->
        if (part.NAME() != null) {
            // It's a parameter
            Pair(list + Declaration.Let(
                toSourceRef(file),
                part.NAME().text,
                id,
                false,
                part.type()?.toTypeRef(),
                part.expression()?.toExpression(file)
            ), id + 1)
        } else {
            // It's an unpacking tuple
            TODO("Unpack parameters")
        }
    }
}

fun YaflParser.AliasContext.toDeclaration(file: String, id: Long, isGlobal: Boolean, prefix: String = ""): Pair<Declaration.Alias, Long> {
    return Pair(Declaration.Alias(
        toSourceRef(file),
        prefix + NAME().text,
        id,
        isGlobal,
        type().toTypeRef()),
        id + 1)
}

fun YaflParser.StructContext.toDeclaration(file: String, id: Long, isGlobal: Boolean, prefix: String = ""): Pair<Declaration.Struct, Long> {
    if (function().isNotEmpty())
        TODO("Struct members")

    val (parameters, nextId) = unpackTuple().toDeclarationLets(file, id)

    TODO("Also declare the struct constructor")

//    return Pair(Declaration.Struct(
//        prefix + NAME().text,
//        nextId,
//        isGlobal,
//        parameters
//    ), nextId + 1)
}

fun YaflParser.FunctionContext.toDeclaration(
    file: String,
    id: Long,
    isGlobal: Boolean,
    prefix: String = ""
): Pair<Declaration.Let, Long> {
    val (parameters, nextId) = unpackTuple().toDeclarationLets(file, id)

    val type = TypeRef.Callable(
        parameter = TypeRef.Tuple(
            fields = parameters.map {
                TupleTypeField(
                    typeRef = it.typeRef,
                    name = it.name
                )
            }
        ),
        result = type()?.toTypeRef()
    )

    return Pair(Declaration.Let(
        toSourceRef(file),
        prefix + NAME().text,
        nextId,
        isGlobal,
        null,
        Expression.Lambda(
            toSourceRef(file),
            type,
            parameters,
            expression().toExpression(file)
        )
    ), nextId + 1)
}

fun YaflParser.LetWithExprContext.toDeclaration(file: String, id: Long, isGlobal: Boolean, prefix: String = ""): Pair<Declaration.Let, Long> {
    return when (val upt = unpackTuple()) {
        null -> Pair(Declaration.Let(
            toSourceRef(file),
            prefix + NAME().text,
            id,
            isGlobal,
            type()?.toTypeRef(),
            expression().toExpression(file)
        ), id + 1)

        else -> throw UnsupportedOperationException()
    }
}


fun YaflParser.DeclarationContext.toDeclaration(file: String, id: Long, isGlobal: Boolean, prefix: String = ""): Pair<Declaration, Long> {
    return alias()?.toDeclaration(file, id, isGlobal, prefix)
        ?: struct()?.toDeclaration(file, id, isGlobal, prefix)
        ?: function()?.toDeclaration(file, id, isGlobal, prefix)
        ?: letWithExpr()?.toDeclaration(file, id, isGlobal, prefix)
        ?: throw IllegalArgumentException()
}
