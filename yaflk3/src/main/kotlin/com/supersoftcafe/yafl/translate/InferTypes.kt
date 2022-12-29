package com.supersoftcafe.yafl.translate


import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Both
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.mapIndexed


class InferTypes(private val typeHints: TypeHints) {

    private fun DataRef.resolveData(
        sourceRef: SourceRef,
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
    ): Pair<DataRef, Declaration.Data?> {
        return when (this) {
            is DataRef.Unresolved -> {
                val foundMany = findDeclarations(name)
                val found = foundMany
                    .filterIsInstance<Declaration.Data>()
                    .filter { it.typeRef.mightBeAssignableTo(receiver) }

                val first = found.firstOrNull()
                if (first == null || found.size > 1)
                    Pair(this, null)
                else
                    Pair(DataRef.Resolved(first.name, first.id, first.scope), first)
            }

            is DataRef.Resolved -> {
                val foundMany = findDeclarations(name)
                Pair(this, foundMany
                    .filterIsInstance<Declaration.Data>()
                    .first { it.id == id && it.scope == scope })
            }
        }
    }


    private fun Expression?.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
    ): Pair<Expression?, TypeHints> {
        return when (this) {
            is Expression.Float, is Expression.Integer, null ->
                Pair(this, emptyTypeHints())

            is Expression.NewKlass -> {
                // Each field of the tuple parameter can add a hint to TypeHints for the target Let for the class
                // The field Lets can build a tuple receiver for the parameter building expression
                // Target class is fixed at parse time, so no inference on this.typeRef.
                val typeRef = typeRef as TypeRef.Named

                val declaration = findDeclarations(typeRef.name).single { it.id == typeRef.id } as Declaration.Klass

                val (parameter, paramHints) = parameter.inferTypes(TypeRef.Tuple(declaration.parameters.map {
                    TupleTypeField(it.typeRef, it.name)
                }), findDeclarations)

                val hints =
                    (parameter?.typeRef as? TypeRef.Tuple)?.fields?.zip(declaration.parameters) { tupleField, paramField ->
                        when (val tr = tupleField.typeRef) {
                            null -> emptyTypeHints()
                            else -> typeHintsOf(paramField.id to TypeHint(sourceRef, inputTypeRef = tr))
                        }
                    }

                Pair(copy(
                    parameter = parameter!!
                ), hints?.fold(paramHints, TypeHints::plus) ?: paramHints)
            }

            is Expression.LoadMember -> {
                val (base, baseHints) = base.inferTypes(null, findDeclarations)

                when (val baseTypeRef = base?.typeRef) {
                    is TypeRef.Named ->
                        when (val declaration =
                            findDeclarations(baseTypeRef.name).single { it.id == baseTypeRef.id }) {
                            is Declaration.Klass -> {
                                (declaration.parameters + declaration.members).firstOrNull {
                                    it.name == name && it.typeRef.mightBeAssignableTo(receiver)
                                }?.let { entry ->
                                    val entryHint = if (receiver != null) {
                                        typeHintsOf(entry.id to TypeHint(sourceRef, outputTypeRef = receiver))
                                    } else {
                                        emptyTypeHints()
                                    }
                                    Pair(copy(
                                        base = base,
                                        typeRef = entry.typeRef,
                                        id = entry.id
                                    ), baseHints + entryHint)
                                }
                            }

                            else -> null
                        }

                    else -> null
                } ?: Pair(copy(base = base!!), baseHints)
            }

            is Expression.BuiltinBinary -> {
                // Binary operator is always well-defined out of the parser
                val (leftExpr, leftHints) = left.inferTypes(op.ltype, findDeclarations)
                val (rightExpr, rightHints) = right.inferTypes(op.rtype, findDeclarations)

                val hints = leftHints + rightHints
                Pair(copy(
                    left = leftExpr!!,
                    right = rightExpr!!
                ), hints)
            }

            is Expression.LoadData -> {
                val (newDataRef, declaration) = dataRef.resolveData(sourceRef, receiver, findDeclarations)
                if (declaration != null && declaration.scope is Scope.Member) {
                    // TODO: Support for nested classes
                    Pair(Expression.LoadMember(
                        sourceRef, typeRef,
                        Expression.LoadData(
                            sourceRef, null,
                            DataRef.Unresolved("this")
                        ),
                        declaration.name,
                        declaration.id
                    ), emptyTypeHints())
                } else {
                    val newTypeRef = mergeTypes(
                        declaration?.sourceTypeRef,
                        inputType = declaration?.typeRef,
                        outputType = receiver
                    )

                    val hints = if (declaration == null || newTypeRef == null) emptyTypeHints()
                    else typeHintsOf(declaration.id to TypeHint(sourceRef, outputTypeRef = newTypeRef))

                    Pair(copy(
                        dataRef = newDataRef,
                        typeRef = newTypeRef
                    ), hints)
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
                val typeRef = mergeTypes(sourceCallableType,
                    inputType = candidateCallableType,
                    outputType = receiver
                )

                val (newBody, bodyHints) = body.inferTypes((typeRef as? TypeRef.Callable)?.result) { name ->
                    parameters.filter { it.name == name } + findDeclarations(name)
                }
                val paramsWithHints = parameters.map { parameter ->
                    parameter.inferTypesLet(findDeclarations)
                }

                val hints = paramsWithHints.fold(bodyHints) { acc, h -> acc + h.second }
                val params = paramsWithHints.map { it.first }
                Pair(copy(
                    typeRef = typeRef,
                    body = newBody!!,
                    parameters = params
                ), hints)
            }

            is Expression.Call -> {
                val typeRef = mergeTypes(
                    null, outputType = receiver,
                    inputType = (callable.typeRef as? TypeRef.Callable)?.result
                )

                val (newCallable, callHints) = callable.inferTypes(
                    TypeRef.Callable(parameter.typeRef as? TypeRef.Tuple, typeRef),
                    findDeclarations
                )
                val (newParameter, paramHints) = parameter.inferTypes(
                    (callable.typeRef as? TypeRef.Callable)?.parameter,
                    findDeclarations
                )
                Pair(copy(
                    callable = newCallable!!,
                    parameter = newParameter!!,
                    typeRef = typeRef
                ), callHints + paramHints)
            }

            is Expression.Tuple -> {
                val typeRef = mergeTypes(null, outputType = receiver, inputType = TypeRef.Tuple(fields.map { field ->
                    TupleTypeField(typeRef = field.expression.typeRef, name = field.name)
                }))
                val typeRefFields = (typeRef as? TypeRef.Tuple)?.fields

                val newFields = fields.mapIndexed { index, field ->
                    val (expression, exprHints) = field.expression.inferTypes(typeRefFields?.getOrNull(index)?.typeRef, findDeclarations)
                    Pair(field.copy(expression = expression!!), exprHints)
                }

                return Pair(copy(
                    typeRef = typeRef,
                    fields = newFields.map { it.first }
                ), newFields.fold(emptyTypeHints()) { acc, (_, h) -> acc + h })
            }

            is Expression.If -> {
                val typeRef = mergeTypes(
                    null,
                    outputTypes = listOfNotNull(receiver),
                    inputTypes = listOfNotNull(ifFalse.typeRef, ifTrue.typeRef)
                )

                val (conditionExpr, condHints) = condition.inferTypes(TypeRef.Primitive(PrimitiveKind.Bool), findDeclarations)
                val (ifFalseExpr, ifFalseHints) = ifFalse.inferTypes(typeRef, findDeclarations)
                val (ifTrueExpr, ifTrueHints) = ifTrue.inferTypes(typeRef, findDeclarations)

                return Pair(copy(
                    typeRef = typeRef,
                    condition = conditionExpr!!,
                    ifTrue = ifTrueExpr!!,
                    ifFalse = ifFalseExpr!!
                ), condHints + ifFalseHints + ifTrueHints)
            }

            else ->
                TODO()
        }
    }


    private fun Declaration.Let.inferTypesLet(
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Declaration.Let, TypeHints> {
        val typeRefOfLet = mergeTypes(
            sourceTypeRef,
            inputTypes  = typeHints.getInputTypeRefs( id) + listOfNotNull(body?.typeRef),
            outputTypes = typeHints.getOutputTypeRefs(id),
        )

        val (body, typeHints) = body.inferTypes(typeRefOfLet, findDeclarations)
        return Pair(copy(
            signature = typeRefOfLet.toSignature(name),
            typeRef = typeRefOfLet,
            body = body,
        ), typeHints)
    }

    private fun Declaration.Function.inferTypesFunction(
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Declaration.Function, TypeHints> {
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

        val (bodyExpr, bodyHints) = body.inferTypes(sourceReturnType ?: returnType) { name ->
            (parameters + thisDeclaration).filter { it.name == name } + findDeclarations(name)
        }
        val params = parameters.map { param ->
            param.inferTypes(findDeclarations)
        }

        return Pair(copy(
            parameters = params.map { (p, _) -> p as Declaration.Let },
            returnType = sourceReturnType ?: bodyExpr?.typeRef,
            body = bodyExpr,
        ), params.fold(bodyHints + paramHints) { acc, (_, h) -> acc + h })
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

    private fun Declaration.Klass.inferTypesKlass(
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Declaration.Klass, TypeHints> {
        val (parameters, parametersHints) = parameters.inferTypesDeclarations(findDeclarations)
        val (members, membersHints) = members.inferTypesDeclarations { name ->
            findMembers(name, findDeclarations) + findDeclarations(name)
        }

        return Pair(copy(
            members = members.filterIsInstance<Declaration.Function>(),
            parameters = parameters.filterIsInstance<Declaration.Let>()
        ), membersHints + parametersHints)
    }

    private fun List<Declaration>.inferTypesDeclarations(
        findDeclarations: (String) -> List<Declaration>
    ): Pair<List<Declaration>, TypeHints> {
        val result = map { it.inferTypes(findDeclarations) }
        return Pair(result.map { (d, _) -> d }, result.fold(TypeHints()) { acc, (_, h) -> acc + h })
    }

    private fun Declaration.inferTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Declaration, TypeHints> {
        return when (this) {
            is Declaration.Let ->
                inferTypesLet(findDeclarations)

            is Declaration.Function ->
                inferTypesFunction(findDeclarations)

            is Declaration.Klass ->
                inferTypesKlass(findDeclarations)

            is Declaration.Alias ->
                // In theory nothing references the alias declarations after the "resolveTypes" stage
                Pair(this, emptyTypeHints())

            else ->
                TODO()
        }
    }

    fun inferTypesInternal(ast: Ast): Ast {
        val result = ast.declarations.map { (imports, declaration, file) ->
            val (declaration, typeHints) = declaration.inferTypes(ast.findDeclarations(imports))
            Pair(Root(imports, declaration, file), typeHints)
        }

        return ast.copy(
            declarations = result.map { it.first },
            typeHints = result.fold(TypeHints()) { acc, value ->
                acc + value.second
            }
        )
    }
}

private fun inferTypes2(ast: Ast): Ast {
    val result = InferTypes(ast.typeHints).inferTypesInternal(ast)

    return if (ast != result)
        inferTypes2(result)
    else result
}

fun inferTypes(ast: Ast): Either<Ast, List<String>> {
    val result = inferTypes2(ast)
    val errors = scanForErrors(result)

    return if (errors.isEmpty())
         Either.Some(result)
    else Either.Error(errors)
}