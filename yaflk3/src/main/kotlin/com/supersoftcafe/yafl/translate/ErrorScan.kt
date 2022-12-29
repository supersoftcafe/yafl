package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.Namer


private class ScanForErrors(val globals: Map<Namer, Declaration>, val hints: TypeHints) {
    private fun TypeRef?.scan(sourceRef: SourceRef): List<String> {
        return when (this) {
            null ->
                listOf("$sourceRef unknown type")

            is TypeRef.Unresolved ->
                listOf("$sourceRef unresolved type '$name'")

            is TypeRef.Tuple ->
                fields.flatMap { it.typeRef.scan(sourceRef) }

            is TypeRef.Callable ->
                result.scan(sourceRef) + parameter.scan(sourceRef)

            is TypeRef.Named ->
                listOf()

            is TypeRef.Primitive ->
                listOf()

            TypeRef.Unit ->
                listOf()
        }
    }

    private fun DataRef?.scan(sourceRef: SourceRef): List<String> {
        return when (this) {
            null ->
                listOf("$sourceRef unknown reference")

            is DataRef.Unresolved ->
                listOf("$sourceRef unresolved reference '$name'")

            is DataRef.Resolved ->
                listOf()
        }
    }


    private fun Expression.scan(): List<String> {
        return when (this) {
            is Expression.NewKlass -> listOf<String>()  // Only exists in generated code, so should never have errors
            is Expression.Characters -> listOf<String>()
            is Expression.Integer -> listOf<String>()
            is Expression.Float -> listOf<String>()

            is Expression.If ->
                (condition.scan() + ifTrue.scan() + ifFalse.scan()).ifEmpty {
                    listOfNotNull(
                        if (condition.typeRef != TypeRef.Primitive(PrimitiveKind.Bool))
                            "${condition.sourceRef} is not a boolean expression"
                        else null,
                        if (typeRef == null)
                            "$sourceRef conditional branch types are not compatible"
                        else null
                    )
                }

            is Expression.Tuple ->
                fields.flatMap { it.expression.scan() }

            is Expression.Call ->
                (callable.scan() + parameter.scan()).ifEmpty {
                    val targetParams = (callable.typeRef as TypeRef.Callable).parameter!!.fields
                    val sourceParams = (parameter.typeRef as TypeRef.Tuple).fields

                    if (targetParams.size != sourceParams.size) {
                        listOf("${parameter.sourceRef} parameter count does not match function requirements")
                    } else {
                        targetParams.mapIndexedNotNull { index, target ->
                            val source = sourceParams[index]
                            if (!target.typeRef.isAssignableFrom(source.typeRef))
                                "${parameter.sourceRef} parameter $index does not match target type"
                            else null
                        }
                    }
                }

            is Expression.BuiltinBinary ->
                (left.scan() + right.scan()).ifEmpty {
                    listOfNotNull(
                        if (left.typeRef  != op.ltype)
                            "${left .sourceRef} does not match operator type"
                        else null,
                        if (right.typeRef != op.rtype)
                            "${right.sourceRef} does not match operator type"
                        else null
                    )
                }

            is Expression.Lambda ->
                parameters.flatMap { it.scan() } + body.scan()

            is Expression.LoadData ->
                dataRef.scan(sourceRef)

            is Expression.LoadMember ->
                base.scan().ifEmpty {
                    listOfNotNull(
                        if (id == null) "$sourceRef member $name not found" else null
                    )
                }

            is Expression.NewStruct -> TODO()
        }.ifEmpty {
            typeRef.scan(sourceRef)
        }
    }

    private fun Declaration.Function.scanFunction(): List<String> {
        return thisDeclaration.scanLet() +
                parameters.flatMap { it.scanLet() } +
                (body?.scan() ?: listOf()).ifEmpty {
                    returnType.scan(sourceRef).ifEmpty {
                        if (body == null || returnType.isAssignableFrom(body.typeRef)) listOf()
                        else listOf("$sourceRef incompatible unction return type and expression")
                    }
                }
    }

    private fun Declaration.Let.scanLet(): List<String> {
        // Try not to return too many errors. If the expression body has an error, don't
        // then also report the almost inevitable type errors on the declaration or assignment.
        return (body?.scan() ?: listOf()).ifEmpty {
            typeRef.scan(sourceRef).ifEmpty {
                if (body == null || typeRef.isAssignableFrom(body.typeRef)) listOf()
                else listOf("$sourceRef incompatible types between let and expression")
            }
        }
    }

    private fun Declaration.Alias.scanAlias(): List<String> {
        return typeRef.scan(sourceRef)
    }

    private fun Declaration.Klass.scanKlass(): List<String> {
        return parameters.flatMap { it.scanLet() } +
                members.flatMap { it.scanFunction() } +
                extends.flatMap { it.scan(sourceRef) }.ifEmpty {
                    // If there have been no errors in the inherited interfaces, check for correct function overrides etc
                    if (extends.filterIsInstance<TypeRef.Named>().any { globals[it.id]?.scan()?.isEmpty() != true }) {
                        listOf()
                    } else {
                        val members = flattenClassMembersBySignature { name, id -> globals[id]!! }

                        members
                            // No ambiguity with duplicate inherited implementations
                            .filterValues { it.size > 1 }
                            .map { (key, list) ->
                                val func = list.first()
                                "${func.sourceRef} Multiple implementations of ${func.name}"
                            } + if (isInterface) listOf() else
                                // No unimplemented functions
                                members
                                    .filterValues { it.first().body == null }
                                    .map { (key, list) ->
                                        val func = list.first()
                                        "${func.sourceRef} Unimplemented"
                                    }
                    }
                }
    }

    private fun Declaration.scan(): List<String> {
        return when (this) {
            is Declaration.Function -> scanFunction()
            is Declaration.Let -> scanLet()
            is Declaration.Klass -> scanKlass()
            is Declaration.Alias -> scanAlias()
        }
    }

    fun scan(ast: Ast): List<String> {
        return ast.declarations.flatMap { (_, declaration, _) ->
            declaration.scan()
        }
    }
}



fun scanForErrors(ast: Ast): List<String> {
    return ScanForErrors(
        ast.declarations.associate { (_, declaration, _) -> declaration.id to declaration },
        ast.typeHints
    ).scan(ast)
}
