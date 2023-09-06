package com.supersoftcafe.yafl.passes.p1_parse

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.models.ast.*



fun YaflParser.ValueParamsPartContext.toDeclarationLet(
    file: String, id: Namer,
    scope: Scope, prefix: String = ""
): Declaration.Let {
    val declare = valueParamsDeclare()
    val sourceRef = toSourceRef(file)
    return declare
        ?. toDeclarationLet(file, id, scope, prefix)?.unwrapSingleton()
        ?: Declaration.Let(
            sourceRef = sourceRef,
            name = prefix + NAME().text,
            id = id + 1,
            scope = scope,
            typeRef = null,
            sourceTypeRef = type()?.toTypeRef(),
            body = valueParamsBody()?.expression()?.toExpression(file, id + 2),
            dynamicArraySize = valueParamsArray()?.expression()?.toExpression(file, id + 3),
            arraySize = valueParamsArray()?.INTEGER()?.parseToInteger(sourceRef)?.value,
        )
}

fun YaflParser.ValueParamsDeclareContext.toDeclarationLet(
    file: String, id: Namer,
    scope: Scope, prefix: String = ""
): Declaration.Let {
    return Declaration.Let.unpack(
        sourceRef = toSourceRef(file),
        values =  valueParamsPart().mapIndexed { index, part ->
            part.toDeclarationLet(file, id + index, scope, prefix)
        })
}

fun YaflParser.AliasContext.toDeclaration(
    file: String, id: Namer,
    scope: Scope, prefix: String = ""
): List<Declaration.Alias> {
    return listOf(
        Declaration.Alias(
        sourceRef = toSourceRef(file),
        name = prefix + NAME().text,
        id = id,
        scope = scope,
        typeRef = type().toTypeRef(),
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

    val interfaceName = prefix + NAME().text
    val interfaceType = TypeRef.Unresolved(interfaceName, interfaceId)
    val scopeOfMembers = Scope.Member(interfaceId, if (scope is Scope.Member) scope.level + 1 else 0)

    val members = classMember().flatMapIndexed { index, member ->
        member.functionTail().toDeclaration(file, memberId + index, scopeOfMembers, interfaceType)
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

    val klassSourceRef = toSourceRef(file)
    val constrSourceRef = valueParamsDeclare()?.toSourceRef(file) ?: klassSourceRef

    val klassName = prefix + NAME().text
    val klassTypeForKlass = TypeRef.Unresolved(klassName, klassId)
    val klassTypeForConstructor = TypeRef.Unresolved(klassName, klassId)

    val scopeOfMembers = Scope.Member(klassId, if (scope is Scope.Member) scope.level + 1 else 0)

    val parameter = valueParamsDeclare().toDeclarationLet(file, parameterId, scopeOfMembers)
    val members = classMember().flatMapIndexed { index, classMember ->
        classMember.functionTail().toDeclaration(file, memberId + index, scopeOfMembers, klassTypeForKlass)
    }

    val klass = Declaration.Klass(
        klassSourceRef,
        klassName,
        klassId,
        scope,
        parameter.flatten(), // default value applies to constructor function
        members,
        extends_().toExtends(),
        isInterface = false,
    )

    // Constructor params need to have different ids and slight modifications for arrays
    val constrParam = parameter.map {
        it.copy(
            dynamicArraySize = null, // array size can only be used by NewKlass and not constructor function
            arraySize = null,
            scope = Scope.Local,
            id = constructorId / it.id,
            sourceTypeRef =
                if (it.arraySize != null)
                    TypeRef.Callable(TypeRef.Tuple(listOf(TupleTypeField(TypeRef.Int32, null))), it.sourceTypeRef)
                else it.sourceTypeRef,
        )
    }

    val constructor = Declaration.Function(
        sourceRef = constrSourceRef,
        name = klassName,
        id = constructorId,
        scope = scope,
        thisDeclaration = Declaration.Let.newThis(
            sourceRef = constrSourceRef,
            id = thisId,
            typeRef = TypeRef.Unit,
        ),
        parameter = constrParam,
        returnType = null,
        sourceReturnType = klassTypeForConstructor,
        body = Expression.NewKlass(
            sourceRef = constrSourceRef,
            typeRef = klassTypeForConstructor,
            parameter = Expression.Tuple(
                sourceRef = constrSourceRef,
                typeRef = TypeRef.Tuple(constrParam.flatten().map {
                    TupleTypeField(
                        typeRef = it.sourceTypeRef,
                        name = it.name
                    )
                }),
                fields = constrParam.flatten().map {
                    TupleExpressionField(
                        name = it.name,
                        expression = Expression.LoadData(
                            sourceRef = constrSourceRef,
                            typeRef = it.sourceTypeRef,
                            dataRef = DataRef.Resolved(it.name, it.id, it.scope),
                        )
                    )
                }
            ),
        ),
    )

    return listOf(klass, constructor)
}

fun YaflParser.FunctionTailContext.toDeclaration(
    file: String, namer: Namer,
    scope: Scope, thisType: TypeRef,
    prefix: String = ""
): List<Declaration.Function> {
    val sourceRef = toSourceRef(file)
    val extensionType = extensionType?.toTypeRef()
    val thisType = if (thisType == TypeRef.Unit && extensionType != null) extensionType else thisType

    return listOf(
        Declaration.Function(
        sourceRef = sourceRef,
        name = prefix + NAME().text,
        id = namer + 3,
        scope = scope,
        thisDeclaration = Declaration.Let.newThis(
            sourceRef = sourceRef,
            id = namer + 1,
            typeRef = thisType
        ),
        parameter = valueParamsDeclare().toDeclarationLet(file, namer + 2, Scope.Local),
        returnType = null,
        sourceReturnType = type()?.toTypeRef(),
        body = expression()?.toExpression(file, namer + 4),
        attributes = attributes()?.NAME()?.map { it.text }?.toSet() ?: setOf(),
        extensionType = extensionType,
    ))
}

fun YaflParser.LetContext.toDeclaration(
    file: String, namer: Namer,
    scope: Scope, prefix: String = ""
): Declaration.Let {
    return valueParamsPart().toDeclarationLet(file, namer, scope, prefix)
}

fun YaflParser.EnumContext.toDeclaration(
    file: String,
    ids: Namer,
    scope: Scope,
    prefix: String = ""
): List<Declaration> {
    val (enumId, memberIds) = ids.fork();

    val enumName = prefix + NAME().text
    val enumTypeRef = TypeRef.Enum(enumName, enumId)

    val members = enumMember().mapIndexed { index, member ->
        val (builderId, memberId, thisId, parameterIds) = (memberIds + index).fork()

        val memberName = member.NAME().text
        val scopeOfMembers = Scope.Member(enumId, if (scope is Scope.Member) scope.level + 1 else 0)
        val parameter = member.valueParamsDeclare()?.toDeclarationLet(file, memberId, scopeOfMembers) ?: Declaration.Let.EMPTY
        val builderSourceRef = member.toSourceRef(file)

        val builder = Declaration.Function(
            sourceRef = builderSourceRef,
            name = prefix + memberName,
            id = builderId,
            scope = scope,
            thisDeclaration = Declaration.Let.newThis(builderSourceRef, thisId, typeRef = TypeRef.Unit),
            parameter = parameter.map {
                it.copy(
                    scope = Scope.Local,
                    id = builderId / parameterIds
                )
            },
            returnType = enumTypeRef,
            sourceReturnType = enumTypeRef,
            body = Expression.NewEnum(
                sourceRef = builderSourceRef,
                typeRef = enumTypeRef,
                tag = memberName,
                parameter = Expression.Tuple(
                    sourceRef = builderSourceRef,
                    typeRef = TypeRef.Tuple(parameter.flatten().map {
                        TupleTypeField(
                            typeRef = it.sourceTypeRef,
                            name = it.name
                        )
                    }),
                    fields = parameter.flatten().map {
                        TupleExpressionField(
                            name = it.name,
                            expression = Expression.LoadData(
                                sourceRef = builderSourceRef,
                                typeRef = it.typeRef,
                                dataRef = DataRef.Resolved(it.name, it.id, it.scope)
                            )
                        )
                    }
                )
            )
        )

        Pair(EnumEntry(memberName, parameter.flatten()), builder)
    }

    val result = members.map { (_, builder) -> builder } + Declaration.Enum(
        sourceRef = toSourceRef(file),
        name = enumName,
        id = enumId,
        scope = scope,
        members = members.map { (member, ) -> member },
    )

    return result
}

fun YaflParser.DeclarationContext.toDeclaration(
    file: String, id: Namer, scope: Scope, prefix: String = ""
): List<Declaration> {
    return alias()?.toDeclaration(file, id, scope, prefix)
        ?: class_()?.toDeclaration(file, id, scope, prefix)
        ?: interface_()?.toDeclaration(file, id, scope, prefix)
        ?: enum_()?.toDeclaration(file, id, scope, prefix)
        ?: function()?.functionTail()?.toDeclaration(file, id, scope, TypeRef.Unit, prefix)
        ?: let()?.toDeclaration(file, id, scope, prefix)?.let { listOf(it) }
        ?: throw IllegalArgumentException()
}
