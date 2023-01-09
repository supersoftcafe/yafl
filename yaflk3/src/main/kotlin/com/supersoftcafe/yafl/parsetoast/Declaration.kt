package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.ast.*

//
//fun YaflParser.EnumContext.toDeclaration(id: Long, isGlobal: Boolean, prefix: String = ""): Pair<Declaration.Enum, Long> {
//    TODO()
//}
//



fun YaflParser.UnpackTupleContext?.toDeclarationLets(
    file: String,
    id: Namer,
    scope: Scope
): List<Declaration.Let> {
    return if (this == null) {
        listOf()
    } else {
        unpackTuplePart().mapIndexed { index, part ->
            if (part.NAME() != null) {
                // It's a parameter
                Declaration.Let(
                    part.toSourceRef(file),
                    part.NAME().text,
                    id + index,
                    scope,
                    null,
                    part.type()?.toTypeRef(),
                    part.expression()?.toExpression(file)
                )
            } else {
                // It's an unpacking tuple
                TODO("Unpack parameters")
            }
        }
    }
}

fun YaflParser.AliasContext.toDeclaration(
    file: String,
    id: Namer,
    scope: Scope,
    prefix: String = ""
): List<Declaration.Alias> {
    return listOf(Declaration.Alias(
        toSourceRef(file),
        prefix + NAME().text,
        id,
        scope,
        type().toTypeRef()))
}


fun YaflParser.ExtendsContext?.toExtends(): List<TypeRef> {
    return if (this == null) {
        listOf()
    } else {
        typeRef().map { it.toTypeRef() }
    }
}

fun YaflParser.InterfaceContext.toDeclaration(
    file: String,
    id: Namer,
    scope: Scope,
    prefix: String = ""
): List<Declaration> {
    val memberId = id + 1
    val interfaceId = id + 2

    val interfaceName = prefix + NAME().text
    val interfaceType = TypeRef.Unresolved(interfaceName, interfaceId)
    val scopeOfMembers = Scope.Member(interfaceId, if (scope is Scope.Member) scope.level + 1 else 0)

    val members = function().flatMapIndexed { index, function ->
        function.toDeclaration(file, memberId + index, scopeOfMembers, interfaceType)
    }

    val sourceRef = toSourceRef(file)
    val declaration = Declaration.Klass(
        sourceRef,
        interfaceName,
        interfaceId,
        scope,
        listOf(),
        members,
        extends_().toExtends(),
        isInterface = true
    )

    return listOf(declaration)
}

fun YaflParser.ClassContext.toDeclaration(
    file: String,
    id: Namer,
    scope: Scope,
    prefix: String = ""
): List<Declaration> {
    val parameterId = id + 1
    val memberId = id + 2
    val klassId = id + 3
    val constructorId = id + 4
    val thisId = id + 5

    val klassName = prefix + NAME().text
    val klassType = TypeRef.Unresolved(klassName, klassId)
    val scopeOfMembers = Scope.Member(klassId, if (scope is Scope.Member) scope.level + 1 else 0)

    val parameters = unpackTuple().toDeclarationLets(file, parameterId, scopeOfMembers)
    val members = classMember().flatMapIndexed { index, classMember ->
        classMember.function().toDeclaration(file, memberId + index, scopeOfMembers, klassType)
    }

    val klassSourceRef = toSourceRef(file)
    val klass = Declaration.Klass(
        klassSourceRef,
        klassName,
        klassId,
        scope,
        parameters,
        members,
        extends_().toExtends(),
        isInterface = false
    )

    val constrSourceRef = unpackTuple()?.toSourceRef(file) ?: klassSourceRef
    val paramType = TypeRef.Tuple(parameters.map { parameter ->
        TupleTypeField(parameter.typeRef, parameter.name)
    })
    val thisDecl = Declaration.Let(constrSourceRef, "this", thisId, Scope.Local, TypeRef.Unit, TypeRef.Unit, null)
    val constrParams = parameters.mapIndexed { index, parameter ->
        parameter.copy(id = constructorId + index, scope = Scope.Local)
    }

    val constructor = Declaration.Function(constrSourceRef, klassName, constructorId, scope, thisDecl, constrParams, null, klassType,
        Expression.NewKlass(constrSourceRef, klassType,
            Expression.Tuple(constrSourceRef, paramType,
                constrParams.map { constrParam ->
                    TupleExpressionField(constrParam.name,
                        Expression.LoadData(constrSourceRef, constrParam.typeRef,
                            DataRef.Resolved(constrParam.name, constrParam.id, constrParam.scope),
                        ),
                    )
                }
            )
        )
    )

    return listOf(klass, constructor)
}

fun YaflParser.FunctionContext.toDeclaration(
    file: String,
    id: Namer,
    scope: Scope,
    thisType: TypeRef,
    prefix: String = ""
): List<Declaration.Function> {
    val sourceRef = toSourceRef(file)
    return listOf(Declaration.Function(
        sourceRef,
        prefix + NAME().text,
        id + 3,
        scope,
        Declaration.Let(sourceRef, "this", id + 1, Scope.Local, thisType, thisType, null),
        unpackTuple().toDeclarationLets(file, id + 2, Scope.Local),
        null,
        type()?.toTypeRef(),
        expression()?.toExpression(file),
        attributes()?.NAME()?.map { it.text }?.toSet() ?: setOf()
    ))
}

fun YaflParser.LetWithExprContext.toDeclaration(
    file: String,
    id: Namer,
    scope: Scope,
    prefix: String = ""
): List<Declaration.Let> {
    return when (val upt = unpackTuple()) {
        null -> listOf(Declaration.Let(
            toSourceRef(file),
            prefix + NAME().text,
            id,
            scope,
            null,
            type()?.toTypeRef(),
            expression().toExpression(file)
        ))

        else -> throw UnsupportedOperationException()
    }
}


fun YaflParser.DeclarationContext.toDeclaration(
    file: String,
    id: Namer,
    scope: Scope,
    prefix: String = ""
): List<Declaration> {
    return alias()?.toDeclaration(file, id, scope, prefix)
        ?: class_()?.toDeclaration(file, id, scope, prefix)
        ?: interface_()?.toDeclaration(file, id, scope, prefix)
        ?: function()?.toDeclaration(file, id, scope, TypeRef.Unit, prefix)
        ?: letWithExpr()?.toDeclaration(file, id, scope, prefix)
        ?: throw IllegalArgumentException()
}
