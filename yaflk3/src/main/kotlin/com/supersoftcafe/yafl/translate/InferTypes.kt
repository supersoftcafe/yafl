package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Both
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.mapIndexed



class InferTypes(private val typeHints: TypeHints) {

    private fun TypeRef?.fuzzyEquals(receiver: TypeRef? ): Boolean {
        return if (receiver == null || this == null) {
            true
        } else when (this) {
            is TypeRef.Named ->
                (receiver as? TypeRef.Named)?.id == id

            is TypeRef.Primitive ->
                (receiver as? TypeRef.Primitive)?.kind == kind

            is TypeRef.Tuple ->
                fields.size == (receiver as? TypeRef.Tuple)?.fields?.size
                        && fields.zip(receiver.fields).all { (l, r) -> l.typeRef.fuzzyEquals(r.typeRef) }

            is TypeRef.Callable ->
                receiver is TypeRef.Callable
                        && result.fuzzyEquals(receiver.result)
                        && parameter.fuzzyEquals(receiver.parameter)

            is TypeRef.Unresolved ->
                throw IllegalStateException("TypeRef.Unresolved should not exist")
        }
    }


    private fun TypeRef?.combineTypes(sourceRef: SourceRef, types: List<TypeRef?>): Both<TypeRef?, String> {
        return when (this) {
            null ->
                (types.lastOrNull { it != null } ?: return Both(null, "$sourceRef undefined type"))
                    .combineTypes(sourceRef, types)

            is TypeRef.Callable -> {
                if (!types.all { it == null || it is TypeRef.Callable }) {
                    Both(this, "$sourceRef type mis-match, expected callable, got $types")
                } else {
                    Both.merge(
                        result.combineTypes(sourceRef, types.map { (it as? TypeRef.Callable)?.result }),
                        parameter.combineTypes(sourceRef, types.map { (it as? TypeRef.Callable)?.parameter })
                    ) { r, p ->
                        Both(copy(result = r, parameter = p as? TypeRef.Tuple))
                    }
                }
            }

            is TypeRef.Tuple ->
                if (!types.all { it == null || (it is TypeRef.Tuple && it.fields.size == fields.size) }) {
                    Both(this, "$sourceRef type mis-match, expected tuple, got $types")
                } else {
                    Both<List<TupleTypeField>, String>(fields)
                        .mapIndexed { index, field ->
                            field.typeRef.combineTypes(sourceRef, types.map { (it as? TypeRef.Tuple)?.fields?.get(index)?.typeRef })
                                .map { Both(field.copy(typeRef = it)) }
                        }
                        .map {
                            Both(copy(fields = it))
                        }
                }

            is TypeRef.Named ->
                Both(this, if (types.all { it == null || it == this })
                    listOf()
                else
                    listOf("$sourceRef type mis-match, expected $name, got $types"))

            is TypeRef.Primitive ->
                Both(this, if (types.all { it == null || it == this })
                    listOf()
                else
                    listOf("$sourceRef type mis-match, expected $kind, got $types"))

            is TypeRef.Unresolved ->
                throw IllegalStateException("TypeRef.Unresolved should not exist")
        }
    }



//
//
//    private fun TypeRef.inferTypes(
//        sourceRef: SourceRef,
//        findDeclarations: (String) -> List<Declaration>
//    ): Both<TypeRef, String> {
//        if (resolved)
//            return Both(this)
//        else when (this) {
//            is TypeRef.Unresolved -> {
//                // Find anything that matches the name and is a type declaration
//                val found = findDeclarations(name)
//                    .filterIsInstance<Declaration.Type>()
//
//                // Locals are strictly ordered, so we take the closest
//                // But globals are not ordered, so we treat ambiguity as an error
//
//                val first = found.firstOrNull()
//                val result: Both<TypeRef, String> = if (first == null) {
//                    Both(this, "$sourceRef Type not found")
//                } else if (first.isGlobal && found.size > 1) {
//                    Both(this, "$sourceRef Ambiguity in type reference, candidates found at ${found.joinToString()}")
//                } else if (first is Declaration.Alias) {
//                    Both(if (first.typeRef.resolved) first.typeRef else this)
//                } else {
//                    Both(TypeRef.Named(first.name, first.id))
//                }
//
//                return result
//            }
//
//            is TypeRef.Tuple ->
//                return Both<List<TupleTypeField>, String>(fields)
//                    .mapIndexed { index, field ->
//                        field.typeRef?.inferTypes(sourceRef, findDeclarations)?.map { Both(field.copy(typeRef = it)) }
//                            ?: Both(field, "$sourceRef Unresolved tuple field type")
//                    }
//                    .map { fields ->
//                        Both(copy(fields = fields))
//                    }
//
//            is TypeRef.Callable ->
//                return Both.merge(
//                    parameter.inferTypes(sourceRef, findDeclarations),
//                    result?.inferTypes(sourceRef, findDeclarations) ?: Both<TypeRef?, String>(null)
//                ) { p, r ->
//                    Both(
//                        copy(parameter = p as TypeRef.Tuple, result = r),
//                        if (r == null || !r.resolved)
//                            listOf("$sourceRef Unresolved return value")
//                        else
//                            listOf()
//                    )
//                }
//
//            // These are already resolved
//            is TypeRef.Named ->
//                return Both(this)
//
//            is TypeRef.Primitive ->
//                return Both(this)
//        }
//    }


    private fun DataRef.resolveData(
        sourceRef: SourceRef,
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
    ): Both<Pair<DataRef, Declaration.Data?>, String> {
        return when (this) {
            is DataRef.Unresolved -> {
                val found = findDeclarations(name)
                    .filterIsInstance<Declaration.Data>()
                    .filter { it is Declaration.Let && receiver.fuzzyEquals(it.typeRef) }

                // Locals are strictly ordered, so we take the closest
                // But globals are not ordered, so we treat ambiguity as an error
                // TODO: Members of a class are not ordered.  What should we do there?

                val first = found.firstOrNull()
                if (first == null)
                    Both(Pair(this, null), "$sourceRef Data reference not found")
                else if (first.isGlobal && found.size > 1)
                    Both(Pair(this, null), "$sourceRef Ambiguity in data reference")
                else if (first.isGlobal)
                    Both(Pair(DataRef.Global(first.name, first.id), first))
                else
                    Both(Pair(DataRef.Local(first.name, first.id), first))
            }

            is DataRef.Global -> {
                val found = findDeclarations(name)
                    .filterIsInstance<Declaration.Data>()
                    .first { it.id == id }
                Both(Pair(this, found))
            }

            is DataRef.Local -> {
                val found = findDeclarations(name)
                    .filterIsInstance<Declaration.Data>()
                    .first { it.id == id }
                Both(Pair(this, found))
            }
        }
    }


    private fun Expression?.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
    ): Both<Pair<Expression?, TypeHints>, String> {
        return when (this) {
            is Expression.Float, is Expression.Integer, null ->
                Both(Pair(this, emptyTypeHints()))

            is Expression.BuiltinBinary -> {
                typeRef.combineTypes(sourceRef, listOf(receiver)).map { typeRef ->
                    Both.merge(
                        left.inferTypes(op.ltype, findDeclarations),
                        right.inferTypes(op.rtype, findDeclarations)
                    ) { (leftExpr, leftHints), (rightExpr, rightHints) ->
                        val hints = leftHints + rightHints
                        Both(Pair(copy(typeRef = typeRef, left = leftExpr!!, right = rightExpr!!), hints))
                    }
                }
            }

            is Expression.LoadData -> {
                dataRef.resolveData(sourceRef, receiver, findDeclarations).map { (dataRef, declaration) ->
                    typeRef.combineTypes(sourceRef, listOf(receiver, (declaration as? Declaration.Let)?.typeRef)).map { typeRef ->
                        val hints = if (declaration != null && typeRef != null)
                             typeHintsOf(declaration.id to TypeHint(sourceRef, typeRef))
                        else emptyTypeHints()
                        Both(Pair(copy(dataRef = dataRef, typeRef = typeRef), hints))
                    }
                }
            }

            is Expression.Lambda -> {
                val receiverFields = (receiver as? TypeRef.Callable)?.parameter?.fields
                val candidateCallableType = TypeRef.Callable(TypeRef.Tuple(parameters.map { TupleTypeField(it.typeRef, it.name) }), body.typeRef)
                typeRef.combineTypes(sourceRef, listOf(receiver, candidateCallableType)).map { typeRef ->
                    Both.merge(
                        body.inferTypes((typeRef as? TypeRef.Callable)?.result) { name ->
                            parameters.filter { it.name == name } + findDeclarations(name)
                        },
                        Both<List<Declaration.Let>,String>(parameters).mapIndexed { index, parameter ->
                            parameter.inferTypesLet(receiverFields?.getOrNull(index)?.typeRef, findDeclarations)
                        }
                    ) { (body, bodyHints), paramsWithHints ->
                        val hints = paramsWithHints.fold(bodyHints) { acc, h -> acc + h.second }
                        val params = paramsWithHints.map { it.first }
                        Both(Pair(copy(typeRef = typeRef, body = body!!, parameters = params), hints))
                    }
                }
            }

            is Expression.Call -> {
                typeRef.combineTypes(sourceRef, listOf(receiver, (callable.typeRef as? TypeRef.Callable)?.result)).map { typeRef ->
                    Both.merge(
                        callable.inferTypes(TypeRef.Callable(parameter.typeRef as? TypeRef.Tuple, typeRef), findDeclarations),
                        parameter.inferTypes((callable.typeRef as? TypeRef.Callable)?.parameter, findDeclarations)
                    ) { (callable, callHints), (parameter, paramHints) ->
                        Both(Pair(copy(callable = callable!!, parameter = parameter!!, typeRef = typeRef), callHints + paramHints))
                    }
                }
            }

            is Expression.Tuple -> {
                typeRef.combineTypes(sourceRef, listOf(receiver, TypeRef.Tuple(fields.map { field ->
                    TupleTypeField(typeRef = field.expression.typeRef, name = field.name)
                }))).map { typeRef ->
                    val typeRefFields = (typeRef as? TypeRef.Tuple)?.fields
                    Both<List<TupleExpressionField>,String>(fields).mapIndexed { index, field ->
                        field.expression.inferTypes(typeRefFields?.getOrNull(index)?.typeRef, findDeclarations).map { (expression, exprHints) ->
                            Both(Pair(field.copy(expression = expression!!), exprHints))
                        }
                    }.map { fields ->
                        Both(Pair(copy(typeRef = typeRef, fields = fields.map { it.first }), fields.fold(emptyTypeHints()) { acc, (_, h) -> acc + h }))
                    }
                }
            }

            is Expression.If -> {
                typeRef.combineTypes(sourceRef, listOf(receiver, ifFalse.typeRef, ifTrue.typeRef)).map { typeRef ->
                    Both.merge(
                        condition.inferTypes(TypeRef.Primitive(PrimitiveKind.Bool), findDeclarations),
                        ifFalse.inferTypes(typeRef, findDeclarations),
                        ifTrue.inferTypes(typeRef, findDeclarations)
                    ) { (conditionExpr, condHints), (ifFalseExpr, ifFalseHints), (ifTrueExpr, ifTrueHints) ->
                        val hints = condHints + ifFalseHints + ifTrueHints
                        Both(Pair(copy(typeRef = typeRef, condition = conditionExpr!!, ifTrue = ifTrueExpr!!, ifFalse = ifFalseExpr!!), hints))
                    }
                }
            }

            else ->
                TODO()
        }
    }



    private fun Declaration.Let.inferTypesLet(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>
    ): Both<Pair<Declaration.Let, TypeHints>, String> {
        val hints = typeHints.getTypeRefs(id)
        return typeRef.combineTypes(sourceRef, hints + receiver + body?.typeRef).map { typeRefOfLet ->
            body.inferTypes(typeRefOfLet, findDeclarations).map { (body, typeHints) ->
                Both(Pair(copy(typeRef = typeRefOfLet, body = body), typeHints))
            }
        }
    }

    private fun Declaration.inferTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Both<Pair<Declaration, TypeHints>, String> {
        return when (this) {
            is Declaration.Let ->
                inferTypesLet(null, findDeclarations)

            is Declaration.Alias ->
                // In theory nothing references the alias declarations after the "resolveTypes" stage
                Both(Pair(this, emptyTypeHints()))

            else ->
                TODO()
        }
    }

    fun inferTypesInternal(ast: Ast): Both<Ast, String> {
        val result = Both<List<Root>, String>(ast.declarations)
            .mapIndexed { _, (imports, declaration, file) ->
                declaration
                    .inferTypes(ast.findDeclarations(imports))
                    .map { (declaration, typeHints) ->
                        Both(Pair(Root(imports, declaration, file), typeHints))
                    }
            }
            .map {
                Both(ast.copy(
                    declarations = it.map { it.first },
                    typeHints = it.fold(TypeHints()) { acc, value ->
                            acc + value.second
                    }))
            }
        return result
    }
}

private fun inferTypes2(ast: Ast): Both<Ast, String> {
    val result = InferTypes(ast.typeHints)
        .inferTypesInternal(ast)

    return if (ast == result.value)
        result
    else
        inferTypes2(result.value)
}

fun inferTypes(ast: Ast): Either<Ast, List<String>> {
    val result = inferTypes2(ast)

    return if (result.error.isEmpty())
        Either.Some(result.value)
    else
        Either.Error(result.error)
}