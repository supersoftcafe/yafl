package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Both
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.mapIndexed

class ResolveTypes() {

    private fun TypeRef?.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): Both<TypeRef?> {
        return when (this) {
            is TypeRef.Unresolved -> {
                // Find anything that matches the name and is a type declaration
                // If it's a user type, construct a reference to it
                // If it's an alias, take a copy of its target, if the target is not an alias...  no jumping around

                val found = findDeclarations(name)
                    .filterIsInstance<Declaration.Type>()
                    .filter { (id == null || id == it.id) }

                val first = found.firstOrNull()
                if (first == null) {
                    Both(this, "$sourceRef Type not found")
                } else if (found.size > 1) {
                    Both(
                        this,
                        "$sourceRef Ambiguity in type reference, candidates found at ${found.joinToString { it.sourceRef.toString() }}"
                    )
                } else if (first is Declaration.Klass) {
                    val extends = first.extends.filterIsInstance<TypeRef.Named>()
                    if (extends.size != first.extends.size) {
                        Both(this, "${first.name} is not fully resolved")
                    } else {
                        Both(TypeRef.Named(first.name, first.id, extends))
                    }
                } else if (first is Declaration.Alias) {
                    if (first.typeRef.resolved)
                        Both(first.typeRef)
                    else
                        Both(this, "$sourceRef Alias waiting to be resolved")
                } else {
                    throw IllegalStateException("${first.javaClass.name} is not a supported type declaration")
                }
            }

            is TypeRef.Tuple ->
                Both<List<TupleTypeField>>(fields)
                    .mapIndexed { index, field ->
                        field.typeRef
                            ?.resolveTypes(sourceRef, findDeclarations)
                            ?.map { Both(field.copy(typeRef = it)) }
                            ?: Both(field)
                    }
                    .map { fields ->
                        Both(copy(fields = fields))
                    }

            is TypeRef.Callable ->
                Both.merge(
                    parameter.resolveTypes(sourceRef, findDeclarations),
                    result?.resolveTypes(sourceRef, findDeclarations) ?: Both<TypeRef?>(null)
                ) { p, r ->
                    Both(copy(parameter = p as TypeRef.Tuple, result = r))
                }

            null, TypeRef.Unit, is TypeRef.Primitive, is TypeRef.Named ->
                Both(this)
        }
    }

    private fun Expression?.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Both<Expression?> {
        return when (this) {
            null -> Both(null)
            is Expression.Float -> Both(this)
            is Expression.Integer -> Both(this)
            is Expression.Characters -> Both(this)

            is Expression.NewKlass ->
                Both.merge(
                    typeRef.resolveTypes(sourceRef, findDeclarations),
                    parameter.resolveTypes(findDeclarations),
                ) { t, p ->
                    Both(copy(typeRef = t!!, parameter = p!!))
                }

            is Expression.NewStruct ->
                Both.merge(
                    typeRef.resolveTypes(sourceRef, findDeclarations),
                    parameter.resolveTypes(findDeclarations),
                ) { t, p ->
                    Both(copy(typeRef = t!!, parameter = p!!))
                }

            is Expression.Call ->
                Both.merge(
                    typeRef.resolveTypes(sourceRef, findDeclarations),
                    callable.resolveTypes(findDeclarations),
                    parameter.resolveTypes(findDeclarations)
                ) { t, c, p ->
                    Both(copy(typeRef = t, callable = c!!, parameter = p!!))
                }

            is Expression.Tuple ->
                Both.merge(
                    typeRef.resolveTypes(sourceRef, findDeclarations),
                    Both<List<TupleExpressionField>>(fields).mapIndexed { index, field ->
                        field.expression
                            .resolveTypes(findDeclarations)
                            .map {
                                Both(field.copy(expression = it!!))
                            }
                    }
                ) { t, f ->
                    Both(copy(typeRef = t, fields = f))
                }

            is Expression.If ->
                Both.merge(
                    condition.resolveTypes(findDeclarations),
                    ifTrue.resolveTypes(findDeclarations),
                    ifFalse.resolveTypes(findDeclarations)
                ) { c, t, f ->
                    Both(copy(condition = c!!, ifTrue = t!!, ifFalse = f!!))
                }

            is Expression.LoadMember ->
                Both.merge(
                    typeRef.resolveTypes(sourceRef, findDeclarations),
                    base.resolveTypes(findDeclarations)
                ) { t, b ->
                    Both(copy(typeRef = t, base = b!!))
                }

            is Expression.LoadData ->
                typeRef.resolveTypes(sourceRef, findDeclarations).map {
                    Both(copy(typeRef = it))
                }

            is Expression.BuiltinBinary ->
                Both.merge(
                    left.resolveTypes(findDeclarations),
                    right.resolveTypes(findDeclarations)
                ) { l, r ->
                    Both(copy(left = l!!, right = r!!))
                }

            is Expression.Lambda ->
                Both.merge(
                    typeRef.resolveTypes(sourceRef, findDeclarations),
                    body.resolveTypes(findDeclarations),
                    Both<List<Declaration.Let>>(parameters).mapIndexed { index, parameter ->
                        parameter.resolveTypes(findDeclarations)
                    }
                ) { t, b, p ->
                    Both<Expression>(copy(typeRef = t, body = b!!, parameters = p.filterIsInstance<Declaration.Let>()))
                }
        }
    }

    private fun List<TypeRef>.resolveTypeRefs(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): Both<List<TypeRef>> {
        return Both(this).mapIndexed { index, typeRef ->
            typeRef.resolveTypes(sourceRef, findDeclarations).map { Both(it!!) }
        }
    }

    private fun List<Declaration>.resolveDeclarations(
        findDeclarations: (String) -> List<Declaration>
    ): Both<List<Declaration>> {
        return Both(this).mapIndexed { index, declaration ->
            declaration.resolveTypes(findDeclarations)
        }
    }

    private fun Declaration.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Both<Declaration> {
        return when (this) {
            is Declaration.Alias ->
                typeRef.resolveTypes(sourceRef, findDeclarations).map {
                    Both(copy(typeRef = it!!))
                }

//            is Declaration.Struct ->
//                Both.merge(
//                    parameters.resolveDeclarations(findDeclarations),
//                    members.resolveDeclarations { name ->
//                        findDeclarations(name) + parameters.filter { it.name == name }
//                    }
//                ) { p, m ->
//                    Both(copy(
//                        parameters = p.filterIsInstance<Declaration.Let>(),
//                        members = m.filterIsInstance<Declaration.Let>()
//                    ))
//                }

            is Declaration.Klass ->
                Both.merge(
                    parameters.resolveDeclarations(findDeclarations),
                    members.resolveDeclarations { name ->
                        findDeclarations(name) + parameters.filter { it.name == name }
                    },
                    extends.resolveTypeRefs(sourceRef, findDeclarations)
                ) { p, m, e ->
                    Both(
                        copy(
                            parameters = p.filterIsInstance<Declaration.Let>(),
                            members = m.filterIsInstance<Declaration.Function>(),
                            extends = e
                        )
                    )
                }

            is Declaration.Let ->
                Both.merge(
                    sourceTypeRef.resolveTypes(sourceRef, findDeclarations),
                    typeRef.resolveTypes(sourceRef, findDeclarations),
                    body.resolveTypes(findDeclarations)
                ) { s, t, b ->
                    Both(copy(sourceTypeRef = s, typeRef = t, body = b))
                }

            is Declaration.Function ->
                Both.merge(
                    thisDeclaration.resolveTypes(findDeclarations),
                    parameters.resolveDeclarations(findDeclarations),
                    body.resolveTypes(findDeclarations),
                    sourceReturnType.resolveTypes(sourceRef, findDeclarations)
                ) { t, p, b, r ->
                    Both(
                        copy(
                            thisDeclaration = t as Declaration.Let,
                            body = b,
                            parameters = p.filterIsInstance<Declaration.Let>(),
                            sourceReturnType = r
                        )
                    )
                }
        }
    }

    fun resolveTypes(ast: Ast): Both<Ast> {
        val result = Both(ast.declarations).mapIndexed { _, (imports, declaration, file) ->
            declaration
                .resolveTypes(ast.findDeclarations(imports))
                .map { declaration -> Both(Root(imports, declaration, file)) }
        }.map {
            Both(ast.copy(declarations = it))
        }

        return if (ast == result.value) {
            result
        } else {
            resolveTypes(result.value)
        }
    }
}

fun resolveTypes(ast: Ast): Either<Ast, List<String>> {
    val result = ResolveTypes().resolveTypes(ast)

    return if (result.error.isEmpty())
        Either.Some(result.value)
    else
        Either.Error(result.error)
}