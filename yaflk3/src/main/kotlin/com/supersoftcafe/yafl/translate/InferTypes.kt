package com.supersoftcafe.yafl.translate


import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Both
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.mapIndexed


class InferTypes(private val typeHints: TypeHints) {


//
//    /**
//     * Find a common least derived ancestor that works for all the input types.
//     */
//    private fun TypeRef?.combineTypes(
//        sourceRef: SourceRef,
//        types: List<TypeRef?>,
//        mostSpecific: Boolean = false
//    ): Both<TypeRef?> {
//        return when (this) {
//            null -> {
//                val maybeNonNullEntry = types.lastOrNull { it != null }
//                maybeNonNullEntry?.combineTypes(sourceRef, types - maybeNonNullEntry, mostSpecific)
//                    ?: Both(null, "$sourceRef undefined type")
//            }
//
//            TypeRef.Unit -> {
//                if (!types.all { it == null || it == TypeRef.Unit }) {
//                    Both(this, "$sourceRef type mis-match, expected callable, got $types")
//                } else {
//                    Both(this)
//                }
//            }
//
//            is TypeRef.Callable -> {
//                if (!types.all { it == null || it is TypeRef.Callable }) {
//                    Both(this, "$sourceRef type mis-match, expected callable, got $types")
//                } else {
//                    val callableTypes = types.filterIsInstance<TypeRef.Callable>()
//                    Both.merge(
//                        result.combineTypes(sourceRef, callableTypes.map { it.result }, mostSpecific),
//                        parameter.combineTypes(sourceRef, callableTypes.map { it.parameter }, !mostSpecific)
//                    ) { r, p ->
//                        Both(copy(result = r, parameter = p as? TypeRef.Tuple))
//                    }
//                }
//            }
//
//            is TypeRef.Tuple ->
//                if (!types.all { it == null || (it is TypeRef.Tuple && it.fields.size == fields.size) }) {
//                    Both(this, "$sourceRef type mis-match, expected tuple, got $types")
//                } else {
//                    Both(fields)
//                        .mapIndexed { index, field ->
//                            field.typeRef.combineTypes(sourceRef,
//                                types.map { (it as? TypeRef.Tuple)?.fields?.get(index)?.typeRef },
//                                mostSpecific).map { Both(field.copy(typeRef = it)) }
//                        }
//                        .map {
//                            Both(copy(fields = it))
//                        }
//                }
//
//            is TypeRef.Named -> {
//                val namedTypes = types.filterIsInstance<TypeRef.Named>()
//                if (namedTypes.size != types.count { it != null }) {
//                    Both(this, listOf("$sourceRef type mis-match, expected $name, got $types"))
//                } else {
//                    val all = namedTypes + this
//                    val ancestor = if (mostSpecific) all.mostSpecificType() else all.commonLeastDerivedAncestor()
//                    if (ancestor != null)
//                        Both(ancestor)
//                    else
//                        Both(this, listOf("$sourceRef cannot find common ancestor from $name, $types"))
//                }
//            }
//
//            is TypeRef.Primitive ->
//                Both(this, if (types.all { it == null || it == this })
//                    listOf()
//                else
//                    listOf("$sourceRef type mis-match, expected $kind, got $types"))
//
//            is TypeRef.Unresolved ->
//                throw IllegalStateException("TypeRef.Unresolved should not exist")
//        }
//    }



    private fun DataRef.resolveData(
        sourceRef: SourceRef,
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
    ): Both<Pair<DataRef, Declaration.Data?>> {
        return when (this) {
            is DataRef.Unresolved -> {
                val foundMany = findDeclarations(name)
                val found = foundMany
                    .filterIsInstance<Declaration.Data>()
                    .filter { it.typeRef.mightBeAssignableTo(receiver) }

                if (name == "size") {
                    println("Here")
                }

                // Locals are strictly ordered, so we take the closest
                // But globals are not ordered, so we treat ambiguity as an error
                // TODO: Members of a class are not ordered.  What should we do there?

                val first = found.firstOrNull()
                if (first == null)
                    Both(Pair(this, null), "$sourceRef Data reference not found")
                else if (found.size > 1)
                    Both(Pair(this, null), "$sourceRef Ambiguity in data reference")
                else
                    Both(Pair(DataRef.Resolved(first.name, first.id, first.scope), first))
            }

            is DataRef.Resolved -> {
                val foundMany = findDeclarations(name)
                val found = foundMany
                    .filterIsInstance<Declaration.Data>()
                    .firstOrNull { it.id == id && it.scope == scope }
                if (found == null) {
                    throw NoSuchElementException()
                }
                Both(Pair(this, found))
            }
        }
    }


    private fun Expression?.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
    ): Both<Pair<Expression?, TypeHints>> {
        return when (this) {
            is Expression.Float, is Expression.Integer, null ->
                Both(Pair(this, emptyTypeHints()))

            is Expression.NewKlass -> {
                // Each field of the tuple parameter can add a hint to TypeHints for the target Let for the class
                // The field Lets can build a tuple receiver for the parameter building expression
                // Target class is fixed at parse time, so no inference on this.typeRef.
                val typeRef = typeRef as TypeRef.Named

                val declaration = findDeclarations(typeRef.name).single { it.id == typeRef.id } as Declaration.Klass

                parameter.inferTypes(TypeRef.Tuple(declaration.parameters.map {
                    TupleTypeField(it.typeRef, it.name)
                }), findDeclarations).map { (parameter, paramHints) ->

                    val hints =
                        (parameter?.typeRef as? TypeRef.Tuple)?.fields?.zip(declaration.parameters) { tupleField, paramField ->
                            when (val tr = tupleField.typeRef) {
                                null -> emptyTypeHints()
                                else -> typeHintsOf(paramField.id to TypeHint(sourceRef, inputTypeRef = tr))
                            }
                        }

                    Both(Pair(copy(parameter = parameter!!), hints?.fold(paramHints, TypeHints::plus) ?: paramHints))
                }
            }

            is Expression.LoadMember -> {
                base.inferTypes(null, findDeclarations).map { (base, baseHints) ->
                    when (val baseTypeRef = base?.typeRef) {
                        is TypeRef.Named ->
                            when (val declaration =
                                findDeclarations(baseTypeRef.name).single { it.id == baseTypeRef.id }) {
                                is Declaration.Klass -> {
                                    val found = (declaration.parameters + declaration.members).filter {
                                        it.name == name && it.typeRef.mightBeAssignableTo(receiver)
                                    }

                                    val entry = found.firstOrNull()
                                    if (entry == null) {
                                        Both(
                                            Pair(copy(base = base), baseHints),
                                            "Property '${declaration.name}.$name' not found"
                                        )
                                    } else if (found.size > 1) {
                                        Both(
                                            Pair(copy(base = base), baseHints),
                                            "Property '${declaration.name}.$name' is ambiguous"
                                        )
                                    } else {
                                        val entryHint = if (receiver != null) {
                                            typeHintsOf(entry.id to TypeHint(sourceRef, outputTypeRef = receiver))
                                        } else {
                                            emptyTypeHints()
                                        }
                                        Both(
                                            Pair(
                                                copy(base = base, typeRef = entry.typeRef, id = entry.id),
                                                baseHints + entryHint
                                            )
                                        )
                                    }
                                }

                                else ->
                                    Both(Pair(copy(base = base), baseHints), "Base must be class")
                            }

                        else ->
                            Both(Pair(copy(base = base!!), baseHints), "Unresolved or incompatible type")
                    }
                }
            }

            is Expression.BuiltinBinary ->
                // Binary operator is always well-defined out of the parser
                Both.merge(
                    left.inferTypes(op.ltype, findDeclarations),
                    right.inferTypes(op.rtype, findDeclarations)
                ) { (leftExpr, leftHints), (rightExpr, rightHints) ->
                    val hints = leftHints + rightHints
                    Both(Pair(copy(left = leftExpr!!, right = rightExpr!!), hints))
                }

            is Expression.LoadData -> {
                dataRef.resolveData(sourceRef, receiver, findDeclarations).map { (dataRef, declaration) ->
                    if (declaration != null && declaration.scope is Scope.Member) {
                        // TODO: Support for nested classes
                        Both(
                            Pair(
                                Expression.LoadMember(
                                    sourceRef,
                                    typeRef,
                                    Expression.LoadData(
                                        sourceRef,
                                        null,
                                        DataRef.Unresolved("this")
                                    ),
                                    declaration.name,
                                    declaration.id
                                ), emptyTypeHints()
                            )
                        )
                    } else {
                        val typeRef = mergeTypes(
                            declaration?.sourceTypeRef,
                            inputType = declaration?.typeRef,
                            outputType = receiver
                        )

                        val hints = if (declaration != null && typeRef != null)
                            typeHintsOf(declaration.id to TypeHint(sourceRef, outputTypeRef = typeRef))
                        else emptyTypeHints()

                        if (dataRef is DataRef.Resolved && dataRef.name == "Test::Cat") {
                            println("Here")
                        }

                        Both(Pair(copy(dataRef = dataRef, typeRef = typeRef), hints))
                    }
                }
            }

            is Expression.Lambda -> {
                val sourceCallableType = TypeRef.Callable(
                    TypeRef.Tuple(parameters.map { TupleTypeField(it.sourceTypeRef, it.name) }),
                    null
                )
                val candidateCallableType = TypeRef.Callable(
                    TypeRef.Tuple(parameters.map { TupleTypeField(it.typeRef, it.name) }),
                    body.typeRef
                )
                val typeRef = mergeTypes(sourceCallableType, inputType = candidateCallableType, outputType = receiver)

                Both.merge(
                    body.inferTypes((typeRef as? TypeRef.Callable)?.result) { name ->
                        parameters.filter { it.name == name } + findDeclarations(name)
                    },
                    Both<List<Declaration.Let>>(parameters).mapIndexed { index, parameter ->
                        parameter.inferTypesLet(findDeclarations)
                    }
                ) { (body, bodyHints), paramsWithHints ->
                    val hints = paramsWithHints.fold(bodyHints) { acc, h -> acc + h.second }
                    val params = paramsWithHints.map { it.first }
                    Both(Pair(copy(typeRef = typeRef, body = body!!, parameters = params), hints))
                }
            }

            is Expression.Call -> {
                val typeRef = mergeTypes(
                    null, outputType = receiver,
                    inputType = (callable.typeRef as? TypeRef.Callable)?.result
                )

                Both.merge(
                    callable.inferTypes(
                        TypeRef.Callable(parameter.typeRef as? TypeRef.Tuple, typeRef),
                        findDeclarations
                    ),
                    parameter.inferTypes((callable.typeRef as? TypeRef.Callable)?.parameter, findDeclarations)
                ) { (callable, callHints), (parameter, paramHints) ->
                    Both(
                        Pair(
                            copy(callable = callable!!, parameter = parameter!!, typeRef = typeRef),
                            callHints + paramHints
                        )
                    )
                }
            }

            is Expression.Tuple -> {
                val typeRef = mergeTypes(null, outputType = receiver, inputType = TypeRef.Tuple(fields.map { field ->
                    TupleTypeField(typeRef = field.expression.typeRef, name = field.name)
                }))
                val typeRefFields = (typeRef as? TypeRef.Tuple)?.fields

                Both<List<TupleExpressionField>>(fields).mapIndexed { index, field ->
                    field.expression.inferTypes(typeRefFields?.getOrNull(index)?.typeRef, findDeclarations)
                        .map { (expression, exprHints) ->
                            Both(Pair(field.copy(expression = expression!!), exprHints))
                        }
                }.map { fields ->
                    Both(
                        Pair(
                            copy(typeRef = typeRef, fields = fields.map { it.first }),
                            fields.fold(emptyTypeHints()) { acc, (_, h) -> acc + h })
                    )
                }
            }

            is Expression.If -> {
                val typeRef = mergeTypes(
                    null,
                    outputTypes = listOfNotNull(receiver),
                    inputTypes = listOfNotNull(ifFalse.typeRef, ifTrue.typeRef)
                )

                Both.merge(
                    condition.inferTypes(TypeRef.Primitive(PrimitiveKind.Bool), findDeclarations),
                    ifFalse.inferTypes(typeRef, findDeclarations),
                    ifTrue.inferTypes(typeRef, findDeclarations)
                ) { (conditionExpr, condHints), (ifFalseExpr, ifFalseHints), (ifTrueExpr, ifTrueHints) ->
                    val hints = condHints + ifFalseHints + ifTrueHints
                    Both(
                        Pair(
                            copy(
                                typeRef = typeRef,
                                condition = conditionExpr!!,
                                ifTrue = ifTrueExpr!!,
                                ifFalse = ifFalseExpr!!
                            ), hints
                        )
                    )
                }
            }

            else ->
                TODO()
        }
    }


    private fun Declaration.Let.inferTypesLet(
        findDeclarations: (String) -> List<Declaration>
    ): Both<Pair<Declaration.Let, TypeHints>> {
        val typeRefOfLet = mergeTypes(
            sourceTypeRef,
            inputTypes  = typeHints.getInputTypeRefs( id) + listOfNotNull(body?.typeRef),
            outputTypes = typeHints.getOutputTypeRefs(id),
        )

        return body.inferTypes(typeRefOfLet, findDeclarations).map { (body, typeHints) -> Both(Pair(
            copy(typeRef = typeRefOfLet, body = body, signature = typeRefOfLet.toSignature(name)),
            typeHints
        ))}
    }

    private fun Declaration.Function.inferTypesFunction(
        findDeclarations: (String) -> List<Declaration>
    ): Both<Pair<Declaration.Function, TypeHints>> {
//        val typeRefOfFunc = mergeTypes(
//            sourceTypeRef,
//            inputTypes  = typeHints.getInputTypeRefs( id) + listOfNotNull(body?.typeRef?.let { TypeRef.Callable(null, it) }),
//            outputTypes = typeHints.getOutputTypeRefs(id) + listOfNotNull(receiver),
//        ) as? TypeRef.Callable


        // Return type is derived from body only
        // Type hints can only impact parameters

        val paramHints = typeHintsOf(typeHints.getOutputTypeRefs(id).flatMap { typeRef ->
            (typeRef as? TypeRef.Callable)?.parameter?.fields?.mapIndexedNotNull { index, field ->
                field.typeRef?.let { typeRef ->
                    parameters.getOrNull(index)?.let { param ->
                        param.id to TypeHint(sourceRef, inputTypeRef = typeRef)
                    }
                }
            } ?: listOf()
        })


        return Both.merge(
            body.inferTypes(sourceReturnType ?: returnType) { name ->
                (parameters + thisDeclaration).filter { it.name == name } + findDeclarations(name)
            },
            Both(parameters).mapIndexed { index, param ->
                param.inferTypes(findDeclarations)
            }
        ) { (bodyExpr, bodyHints), params -> Both(Pair(
            copy(
                parameters = params.map { (p, _) -> p as Declaration.Let },
                returnType = sourceReturnType ?: bodyExpr?.typeRef,
                body = bodyExpr,
            ),
            params.foldIndexed(bodyHints + paramHints) { index, acc, (_, h) -> acc + h }
        )) }
    }


    private fun Declaration.Klass.findMembers(
        name: String,
        findDeclarations: (String) -> List<Declaration>
    ): List<Declaration> {
        return ((parameters + members).filter { it.name == name } + extends.flatMap { typeRef ->
            if (typeRef is TypeRef.Named)
                (findDeclarations(typeRef.name).first { it.id == typeRef.id } as Declaration.Klass)
                    .findMembers(name, findDeclarations)
            else
                listOf()
        })
            .distinctBy { // Remove duplicates due to diamond inheritance
                it.id
            }

            .distinctBy { // Only closest example of fully resolved function is used, if known
                (it as Declaration.Data).signature ?: it.id.toString()
            }
    }

    private fun Declaration.Klass.checkForInheritanceErrorsInKlass(
        findDeclarations: (String) -> List<Declaration>
    ): List<String> {
        // NOTE: Inheritance is not a path for inference. Inference is required before we can resolve inheritance.
        val membersBySignature = flattenClassMembersBySignature { name, id -> findDeclarations(name).first { it.id == id }}

        val errors = membersBySignature
            .mapNotNull { (signature, members) ->
                if (members.count { it.body != null } > 1)
                    "Class $name has duplicate implementations of $signature"
                else if (!isInterface && members.any { it.body == null })
                    "Class $name has no implementations of $signature"
                else
                    null
            }

        return errors
    }

    private fun Declaration.Klass.inferTypesKlass(
        findDeclarations: (String) -> List<Declaration>
    ): Both<Pair<Declaration.Klass, TypeHints>> {
        return Both.merge(
            members.inferTypesDeclarations() { name -> findMembers(name, findDeclarations) + findDeclarations(name) },
            parameters.inferTypesDeclarations(findDeclarations),
        ) { (members, membersHints), (parameters, parametersHints) ->
            val result = copy(
                members = members.filterIsInstance<Declaration.Function>(),
                parameters = parameters.filterIsInstance<Declaration.Let>()
            )
            Both(
                Pair(result, membersHints + parametersHints),
                result.checkForInheritanceErrorsInKlass(findDeclarations)
            )
        }
    }

    private fun List<Declaration>.inferTypesDeclarations(
        findDeclarations: (String) -> List<Declaration>
    ): Both<Pair<List<Declaration>, TypeHints>> {
        return Both(this).mapIndexed { _, declaration ->
            declaration.inferTypes(findDeclarations)
        }.map {
            Both(Pair(it.map { (d, _) -> d }, it.fold(TypeHints()) { acc, (_, h) -> acc + h }))
        }
    }

    private fun Declaration.inferTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Both<Pair<Declaration, TypeHints>> {
        return when (this) {
            is Declaration.Let ->
                inferTypesLet(findDeclarations)

            is Declaration.Function ->
                inferTypesFunction(findDeclarations)

            is Declaration.Klass ->
                inferTypesKlass(findDeclarations)

            is Declaration.Alias ->
                // In theory nothing references the alias declarations after the "resolveTypes" stage
                Both(Pair(this, emptyTypeHints()))

            else ->
                TODO()
        }
    }

    fun inferTypesInternal(ast: Ast): Both<Ast> {
        val result = Both<List<Root>>(ast.declarations)
            .mapIndexed { _, (imports, declaration, file) ->
                declaration
                    .inferTypes(ast.findDeclarations(imports))
                    .map { (declaration, typeHints) ->
                        Both(Pair(Root(imports, declaration, file), typeHints))
                    }
            }
            .map {
                Both(
                    ast.copy(
                        declarations = it.map { it.first },
                        typeHints = it.fold(TypeHints()) { acc, value ->
                            acc + value.second
                        })
                )
            }
        return result
    }
}

private fun inferTypes2(ast: Ast): Both<Ast> {
    val result = InferTypes(ast.typeHints).inferTypesInternal(ast)

    return if (ast == result.value) {
        // One more for debugging purposes. Discard result.
        InferTypes(ast.typeHints).inferTypesInternal(ast)

        result
    } else {
        inferTypes2(result.value)
    }
}

fun inferTypes(ast: Ast): Either<Ast, List<String>> {
    val result = inferTypes2(ast)

    return if (result.error.isEmpty())
        Either.Some(result.value)
    else
        Either.Error(result.error)
}