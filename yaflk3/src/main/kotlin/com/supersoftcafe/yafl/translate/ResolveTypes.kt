package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Both
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.mapIndexed

class ResolveTypes() {

    private fun TypeRef?.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): Both<TypeRef?, String> {
        return when (this) {
            null ->
                Both(null)

            is TypeRef.Unresolved -> {
                // Find anything that matches the name and is a type declaration
                val found = findDeclarations(name)
                    .filterIsInstance<Declaration.Type>()

                // Locals are strictly ordered, so we take the closest
                // But globals are not ordered, so we treat ambiguity as an error

                val first = found.firstOrNull()
                if (first == null) {
                    Both(this, "$sourceRef Type not found")
                } else if (first.isGlobal && found.size > 1) {
                    Both(this, "$sourceRef Ambiguity in type reference, candidates found at ${found.joinToString { it.sourceRef.toString() }}")
                } else {
                    Both(TypeRef.Named(first.name, first.id))
                }
            }

            is TypeRef.Tuple ->
                Both<List<TupleTypeField>, String>(fields)
                    .mapIndexed { index, field ->
                        field.typeRef
                            ?. resolveTypes(sourceRef, findDeclarations)
                            ?. map { Both(field.copy(typeRef = it)) }
                            ?: Both(field)
                    }
                    .map { fields ->
                        Both(copy(fields = fields))
                    }

            is TypeRef.Callable ->
                Both.merge(
                    parameter.resolveTypes(sourceRef, findDeclarations),
                    result?.resolveTypes(sourceRef, findDeclarations) ?: Both<TypeRef?, String>(null)
                ) { p, r ->
                    Both(copy(parameter = p as TypeRef.Tuple, result = r))
                }

            is TypeRef.Primitive ->
                Both(this)

            is TypeRef.Named -> {
                val declaration = findDeclarations(name).single { it.id == id }
                Both(if (declaration is Declaration.Alias && declaration.typeRef.resolved) declaration.typeRef else this)
            }
        }
    }

    private fun Expression?.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Both<Expression?, String> {
        return when (this) {
            null -> Both(null)
            is Expression.Float -> Both(this)
            is Expression.Integer -> Both(this)
            is Expression.Characters -> Both(this)

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
                    Both<List<TupleExpressionField>,String>(fields).mapIndexed { index, field ->
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
                typeRef.resolveTypes(sourceRef, findDeclarations)
                    .map {
                        Both(copy(typeRef = it))
                    }

            is Expression.Add ->
                Both.merge(
                    typeRef.resolveTypes(sourceRef, findDeclarations),
                    left.resolveTypes(findDeclarations),
                    right.resolveTypes(findDeclarations)
                ) { t, l, r ->
                    Both(copy(typeRef = t, left = l!!, right = r!!))
                }

            is Expression.Lambda ->
                Both.merge(
                    typeRef.resolveTypes(sourceRef, findDeclarations),
                    body.resolveTypes(findDeclarations),
                    Both<List<Declaration.Let>,String>(parameters)
                        .mapIndexed { index, parameter ->
                            parameter.resolveTypes(findDeclarations)
                        }
                ) { t, b, p ->
                    Both(copy(typeRef = t, body = b!!, parameters = p.filterIsInstance<Declaration.Let>()))
                }
        }
    }

    private fun Declaration.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Both<Declaration, String> {
        return when (this) {
            is Declaration.Let ->
                return Both.merge(
                    typeRef.resolveTypes(sourceRef, findDeclarations),
                    body.resolveTypes(findDeclarations)
                ) { t, b ->
                    Both(copy(typeRef = t, body = b))
                }

            is Declaration.Alias ->
                typeRef.resolveTypes(sourceRef, findDeclarations)
                    .map {
                        Both(copy(typeRef = it!!))
                    }

            is Declaration.Struct ->
                Both<List<Declaration.Let>, String>(parameters)
                    .mapIndexed { index, parameter ->
                        parameter.resolveTypes(findDeclarations)
                    }
                    .map {
                        Both(copy(parameters = it.filterIsInstance<Declaration.Let>()))
                    }
        }
    }

    fun resolveTypes(ast: Ast): Both<Ast, String> {
        val result = Both<List<Root>, String>(ast.declarations)
            .mapIndexed { _, (imports, declaration, file) ->
                declaration
                    .resolveTypes(ast.findDeclarations(imports))
                    .map { declaration -> Both(Root(imports, declaration, file)) }
            }
            .map {
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