package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.ast.*


fun List<Declaration.Generic>.forwardGenericParams(): List<TypeRef> {
    return map { genericType ->
        TypeRef.Unresolved(
            name = genericType.name,
            id = genericType.id,
            genericParameters = listOf()
        )
    }
}

fun YaflParser.ValueParamsDeclareContext?.toDeclarationLets(
    file: String,
    namer: Namer,
    scope: Scope
): List<Declaration.Let> {
    return if (this == null) {
        listOf()
    } else {
        valueParamsPart().mapIndexed { index, part ->
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
                    arraySize = part.INTEGER()?.parseToInteger(sourceRef)?.value,

                    genericDeclaration = listOf()
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
        sourceRef = toSourceRef(file),
        name = prefix + NAME().text,
        id = id,
        scope = scope,
        typeRef = type().toTypeRef(),
        genericDeclaration = genericParamsDeclare().toGenericParamsDeclare(file, id + 6),
    ))
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
    val genericsId = id + 6

    val genericDeclaration = genericParamsDeclare().toGenericParamsDeclare(file, genericsId)
    val genericForwardedParams = genericDeclaration.forwardGenericParams()

    val interfaceName = prefix + NAME().text
    val interfaceType = TypeRef.Unresolved(interfaceName, interfaceId, genericForwardedParams)
    val scopeOfMembers = Scope.Member(interfaceId, if (scope is Scope.Member) scope.level + 1 else 0)


    val members = function().flatMapIndexed { index, function ->
        function.toDeclaration(file, memberId + index, scopeOfMembers, interfaceType)
    }

    val sourceRef = toSourceRef(file)
    val declaration = Declaration.Klass(
        sourceRef = sourceRef,
        name = interfaceName,
        id = interfaceId,
        scope = scope,
        parameters = listOf(),
        members = members,
        extends = extends_().toExtends(),
        isInterface = true,
        genericDeclaration = genericDeclaration
    )

    return listOf(declaration)
}

fun YaflParser.GenericParamsDeclareContext?.toGenericParamsDeclare(
    file: String,
    id: Namer,
): List<Declaration.Generic> {
    return this?.NAME()?.mapIndexed { index, terminalNode ->
        val name = terminalNode.text
        Declaration.Generic(
            sourceRef = toSourceRef(file),
            name = name,
            id = id + index,
            scope = Scope.Local,
        )
    } ?: listOf()
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
    val genericsId = id + 6

    val genericDeclaration = genericParamsDeclare().toGenericParamsDeclare(file, genericsId)
    val genericForwardedParams = genericDeclaration.forwardGenericParams()

    val klassName = prefix + NAME().text
    val klassType = TypeRef.Unresolved(klassName, klassId, genericForwardedParams)
    val scopeOfMembers = Scope.Member(klassId, if (scope is Scope.Member) scope.level + 1 else 0)

    val parameters = valueParamsDeclare().toDeclarationLets(file, parameterId, scopeOfMembers)
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
        isInterface = false,
        genericDeclaration = genericDeclaration
    )

    val constrSourceRef = valueParamsDeclare()?.toSourceRef(file) ?: klassSourceRef
    val thisDecl = Declaration.Let(
        sourceRef = constrSourceRef,
        name = "this",
        id = thisId,
        scope = Scope.Local,
        typeRef = TypeRef.Unit,
        sourceTypeRef = TypeRef.Unit,
        body = null,
        genericDeclaration = listOf() // If 'this' is generic, its params are on the TypeRef
    )

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

    val constructor = Declaration.Function(
        sourceRef = constrSourceRef,
        name = klassName,
        id = constructorId,
        scope = scope,
        thisDeclaration = thisDecl,
        parameters = constrParams,
        returnType = null,
        sourceReturnType = klassType,
        body = Expression.NewKlass(
            sourceRef = constrSourceRef,
            typeRef = klassType,
            parameter = Expression.Tuple(
                sourceRef = constrSourceRef,
                typeRef = paramType,
                fields = constrParams.map { constrParam ->
                    TupleExpressionField(
                        name = constrParam.name,
                        expression = Expression.LoadData(
                            sourceRef = constrSourceRef,
                            typeRef = constrParam.sourceTypeRef,
                            dataRef = DataRef.Resolved(constrParam.name, constrParam.id, constrParam.scope),
                            genericParameters = listOf()
                        )
                    )
                }
            ),
            genericParameters = genericForwardedParams
        ),
        genericDeclaration = genericDeclaration
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
        sourceRef = sourceRef,
        name = prefix + NAME().text,
        id = namer + 3,
        scope = scope,
        thisDeclaration = Declaration.Let(
            sourceRef = sourceRef,
            name = "this",
            id = namer + 1,
            scope = Scope.Local,
            typeRef = thisType,
            sourceTypeRef = thisType,
            body = null,
            genericDeclaration = listOf() // If 'this' is generic its type params are on the TypeRef
        ),
        parameters = valueParamsDeclare().toDeclarationLets(file, namer + 2, Scope.Local),
        returnType = null,
        sourceReturnType = type()?.toTypeRef(),
        body = expression()?.toExpression(file, namer + 4),
        attributes = attributes()?.NAME()?.map { it.text }?.toSet() ?: setOf(),
        extensionType = extensionType,
        genericDeclaration = genericParamsDeclare().toGenericParamsDeclare(file, namer + 6),
    ))
}

fun YaflParser.LetContext.toDeclaration(
    file: String,
    namer: Namer,
    scope: Scope,
    prefix: String = ""
): Declaration.Let {
    return Declaration.Let(
        sourceRef = toSourceRef(file),
        name = prefix + NAME().text,
        id = namer + 1,
        scope = scope,
        typeRef = null,
        sourceTypeRef = type()?.toTypeRef(),
        body = expression().toExpression(file, namer + 2),
        genericDeclaration = genericParamsDeclare().toGenericParamsDeclare(file, namer + 6),
    )
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
        ?: let()?.toDeclaration(file, id, scope, prefix)?.let { listOf(it) }
        ?: throw IllegalArgumentException()
}
