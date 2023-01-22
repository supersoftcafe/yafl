package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.ast.*


fun YaflParser.UnpackTupleContext?.toDeclarationLets(
    file: String,
    namer: Namer,
    scope: Scope
): List<Declaration.Let> {
    return if (this == null) {
        listOf()
    } else {
        unpackTuplePart().mapIndexed { index, part ->
            if (part.NAME() != null) {
                val sourceRef = part.toSourceRef(file)
                val id = namer + index

                // It's a parameter
                Declaration.Let(
                    sourceRef,
                    part.NAME().text,
                    id,
                    scope,

                    typeRef = null,
                    sourceTypeRef = part.type()?.toTypeRef(),

                    body = null,

                    dynamicArraySize = part.expression()?.toExpression(file, id),
                    arraySize = part.INTEGER()?.parseToInteger(sourceRef)?.value
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
        parameters.map { it.copy(body = null) }, // default value applies to constructor function
        members,
        extends_().toExtends(),
        isInterface = false
    )

    val constrSourceRef = unpackTuple()?.toSourceRef(file) ?: klassSourceRef
    val thisDecl = Declaration.Let(constrSourceRef, "this", thisId, Scope.Local, TypeRef.Unit, TypeRef.Unit, null)

    // Constructor params need to have different ids and slight modifications for arrays
    val constrParams = parameters.mapIndexed { index, parameter ->
        parameter.copy(
            dynamicArraySize = null, // array size can only be used by NewKlass and not constructor function
            arraySize = null,
            scope = Scope.Local,
            id = constructorId + index,
            sourceTypeRef = if (parameter.arraySize != null)
                   TypeRef.Callable(TypeRef.Tuple(listOf(TupleTypeField(TypeRef.Int32, null))), parameter.sourceTypeRef)
              else parameter.sourceTypeRef,
        )
    }

    val paramType = TypeRef.Tuple(constrParams.map { parameter ->
        TupleTypeField(parameter.sourceTypeRef, parameter.name)
    })

    val constructor = Declaration.Function(constrSourceRef, klassName, constructorId, scope, thisDecl, constrParams, null, klassType,
        Expression.NewKlass(constrSourceRef, klassType,
            Expression.Tuple(constrSourceRef, paramType,
                constrParams.map { constrParam ->
                    TupleExpressionField(constrParam.name,
                        Expression.LoadData(constrSourceRef, constrParam.sourceTypeRef,
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
    namer: Namer,
    scope: Scope,
    thisType: TypeRef,
    prefix: String = ""
): List<Declaration.Function> {
    val sourceRef = toSourceRef(file)
    val extensionType = extensionType?.toTypeRef()
    val thisType = if (thisType == TypeRef.Unit && extensionType != null) extensionType else thisType

    return listOf(Declaration.Function(
        sourceRef,
        prefix + NAME().text,
        namer + 3,
        scope,
        Declaration.Let(sourceRef, "this", namer + 1, Scope.Local, thisType, thisType, null),
        unpackTuple().toDeclarationLets(file, namer + 2, Scope.Local),
        null,
        type()?.toTypeRef(),
        body = expression()?.toExpression(file, namer + 4),
        attributes = attributes()?.NAME()?.map { it.text }?.toSet() ?: setOf(),
        extensionType = extensionType,
    ))
}

fun YaflParser.LetWithExprContext.toDeclaration(
    file: String,
    namer: Namer,
    scope: Scope,
    prefix: String = ""
): Declaration.Let {
    return when (val upt = unpackTuple()) {
        null -> Declaration.Let(
            toSourceRef(file),
            prefix + NAME().text,
            namer + 1,
            scope,
            null,
            type()?.toTypeRef(),
            expression().toExpression(file, namer + 2)
        )

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
        ?: letWithExpr()?.toDeclaration(file, id, scope, prefix)?.let { listOf(it) }
        ?: throw IllegalArgumentException()
}
