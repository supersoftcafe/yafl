package com.supersoftcafe.yafl.translate


import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.invert


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

    private fun List<Expression>.inferTypesExpressions(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>
    ): Pair<List<Expression>, TypeHints> {
        val result = map { it.inferTypes(receiver, findDeclarations) }
        return Pair(result.map { (e, _) -> e!! }, result.fold(emptyTypeHints()) { acc, (_, h) -> acc + h })
    }

    private fun Expression?.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
    ): Pair<Expression?, TypeHints> {
        return when (this) {
            is Expression.RawPointer -> {
                val (field, fieldHints) = field.inferTypes(null, findDeclarations)
                Pair(copy(field = field!!), fieldHints)
            }

            is Expression.Let -> {
                val (let, letHints) = let.inferTypes(findDeclarations)
                val (tail, tailHints) = tail.inferTypes(receiver) { name ->
                    findDeclarations(name) + if (let.name == name) listOf(let) else listOf()
                }
                Pair(copy(let = let as Declaration.Let, tail = tail!!, typeRef = tail.typeRef), letHints + tailHints)
            }

            is Expression.Assert -> {
                val (value, valueHints) = value.inferTypes(receiver, findDeclarations)
                val (condition, conditionHints) = condition.inferTypes(TypeRef.Bool, findDeclarations)
                Pair(copy(value = value!!, condition = condition!!, typeRef = value.typeRef), valueHints + conditionHints)
            }

            is Expression.ArrayLookup -> {
                val (array, arrayHints) = array.inferTypes(receiver, findDeclarations)
                val (index, indexHints) = index.inferTypes(TypeRef.Int32, findDeclarations)
                Pair(copy(array = array!!, index = index!!, typeRef = array.typeRef), arrayHints + indexHints)
            }

            is Expression.Float, is Expression.Integer, is Expression.Characters, null ->
                Pair(this, emptyTypeHints())

            is Expression.NewKlass -> {
                val typeRef = typeRef as TypeRef.Named

                val declaration = findDeclarations(typeRef.name).single { it.id == typeRef.id } as Declaration.Klass

                val (parameter, paramHints) = parameter.inferTypes(TypeRef.Tuple(declaration.parameters.map {
                    TupleTypeField(if (it.arraySize != null) {
                        // Array requires a lambda parameter
                        TypeRef.Callable(TypeRef.Tuple(listOf(TupleTypeField(TypeRef.Int32, null))), it.typeRef)
                    } else {
                        // Otherwise just the value
                        it.typeRef
                    }, it.name)
                }), findDeclarations)

                val hints = (parameter?.typeRef as? TypeRef.Tuple)?.fields
                    ?.zip(declaration.parameters) { tupleField, paramField ->
                        when (val tr = tupleField.typeRef) {
                            null -> emptyTypeHints()
                            else -> {
                                typeHintsOf(paramField.id to TypeHint(inputTypeRef = if (paramField.arraySize != null) {
                                    // Array member hint is the lambda return type
                                    (tr as? TypeRef.Callable)?.result
                                } else {
                                    // Otherwise just the type
                                    tr
                                }))
                            }
                        }
                    }

                Pair(copy(
                    parameter = parameter as Expression.Tuple
                ), hints?.fold(paramHints, TypeHints::plus) ?: paramHints)
            }

            is Expression.LoadMember -> {
                val (base, baseHints) = base.inferTypes(null, findDeclarations)

                when (val baseTypeRef = base?.typeRef) {
                    is TypeRef.Named ->
                        when (val declaration = findDeclarations(baseTypeRef.name).single { it.id == baseTypeRef.id }) {
                            is Declaration.Klass -> {

                                val candidatesByName =
                                    // Candidate member functions
                                    (declaration.parameters + declaration.members).filter { it.name == name } +
                                    // Candidate extension functions
                                    findDeclarations(name).filterIsInstance<Declaration.Function>().filter {
                                        it.thisDeclaration.typeRef.isAssignableFrom(declaration)
                                    }

                                // TODO: Also search extends hierarchy
                                candidatesByName.singleOrNull {
                                    it.typeRef.mightBeAssignableTo(receiver)
                                }?.let { entry ->

                                    val entryHint = if (receiver != null) {
                                        typeHintsOf(entry.id to TypeHint(outputTypeRef = receiver))
                                    } else {
                                        emptyTypeHints()
                                    }

                                    Pair(copy(
                                        base = base,
                                        typeRef = if (entry.typeRef?.complete == true) entry.typeRef else typeRef,
                                        id = entry.id
                                    ), baseHints + entryHint)

                                }
                            }

                            else -> null
                        }

                    else -> null
                } ?: Pair(copy(base = base!!), baseHints)
            }

            is Expression.Llvmir -> {
                val newInputs = inputs.map { it.inferTypes(null, findDeclarations) }
                val hints = newInputs.fold(emptyTypeHints()) { acc, (expr, hints) -> acc + hints }
                Pair(copy(
                    inputs = newInputs.map { (expr, hints) -> expr!! }
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
                            DataRef.Unresolved("this"),
                        ),
                        declaration.name,
                        declaration.id,
                    ), emptyTypeHints())
                } else {
                    val newTypeRef = mergeTypes(
                        declaration?.sourceTypeRef,
                        inputType = declaration?.typeRef,
                        outputType = receiver
                    )

                    val hints = if (declaration == null || newTypeRef == null) emptyTypeHints()
                    else typeHintsOf(declaration.id to TypeHint(outputTypeRef = newTypeRef))

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

                // TODO: TypeRef found the correct param type, but it didn't make it to the Let param
                //       Why?

                val (newBody, bodyHints) = body.inferTypes((typeRef as? TypeRef.Callable)?.result) { name ->
                    parameters.filter { it.name == name } + findDeclarations(name)
                }
                val paramsWithHints = parameters.map { parameter ->
                    parameter.inferTypesLet(findDeclarations)
                }

                val hints = paramsWithHints.fold(bodyHints) { acc, h -> acc + h.second }
                val params = paramsWithHints.map { it.first }

                val typeRefHints = typeHintsOf(((typeRef as? TypeRef.Callable)?.parameter?.fields ?: listOf()).zip(params).map {
                        (hint, param) -> param.id to TypeHint(inputTypeRef = hint.typeRef)
                })

                Pair(copy(
                    typeRef = typeRef,
                    body = newBody!!,
                    parameters = params
                ), hints + typeRefHints)
            }

            is Expression.Call -> {
                val typeRef = mergeTypes(
                    null,
                    outputType = receiver,
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
                    parameter = newParameter as Expression.Tuple,
                    typeRef = typeRef
                ), callHints + paramHints)
            }

            is Expression.Parallel -> {
                val (newParameter, paramHints) = parameter.inferTypes(receiver, findDeclarations)
                Pair(copy(
                    parameter = newParameter as Expression.Tuple,
                    typeRef = newParameter.typeRef
                ), paramHints)
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

                val (conditionExpr, condHints) = condition.inferTypes(TypeRef.Bool, findDeclarations)
                val (ifFalseExpr, ifFalseHints) = ifFalse.inferTypes(typeRef, findDeclarations)
                val (ifTrueExpr, ifTrueHints) = ifTrue.inferTypes(typeRef, findDeclarations)

                return Pair(copy(
                    typeRef = typeRef,
                    condition = conditionExpr!!,
                    ifTrue = ifTrueExpr!!,
                    ifFalse = ifFalseExpr!!
                ), condHints + ifFalseHints + ifTrueHints)
            }
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
        val (dynamicArraySize, dynamicArraySizeHints) = dynamicArraySize.inferTypes(TypeRef.Int32, findDeclarations)

        return Pair(copy(
            dynamicArraySize = dynamicArraySize,
            signature = typeRefOfLet.toSignature(name),
            typeRef = typeRefOfLet,
            body = body
        ), typeHints + dynamicArraySizeHints)
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
                        param.id to TypeHint(inputTypeRef = typeRef)
                    }
                }
            } ?: listOf()
        })

        val (bodyExpr, bodyHints) = body.inferTypes(sourceReturnType ?: returnType) { name ->
            (parameters + thisDeclaration).filter { it.name == name } + findDeclarations(name)
        }
        val (params, paramHints2) = parameters.inferTypesParameters(findDeclarations)

        return Pair(copy(
            parameters = params,
            returnType = sourceReturnType ?: bodyExpr?.typeRef,
            body = bodyExpr,
        ), bodyHints + paramHints + paramHints2)
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
        // Parameters can only see other parameters to the left of their position
        val (parameters, parametersHints) = parameters.inferTypesParameters(findDeclarations)

        // Members can see all parameters and all members
        val (members, membersHints) = members.inferTypesMembers { name ->
            findMembers(name, findDeclarations) + findDeclarations(name)
        }

        return Pair(copy(
            members = members,
            parameters = parameters
        ), membersHints + parametersHints)
    }

    private fun List<Declaration.Let>.inferTypesParameters(
        findDeclarations: (String) -> List<Declaration>
    ): Pair<List<Declaration.Let>, TypeHints> {
        // Default expressions and array size expressions can see parameters to the left. That's what makes it
        // different to inferTypesMembers, which can see all members simultaneously. Parameters can't see to the
        // right. This is true for both class and function parameters.

        return if (isEmpty()) {
            Pair(listOf(), emptyTypeHints())
        } else {
            val (headParam, headHints) = first().inferTypesLet(findDeclarations)
            val (tailParams, tailHints) = drop(1).inferTypesParameters { name ->
                if (name == headParam.name)
                    // Change scope to local for klass due to its duality as a member and a local
                    listOf(headParam.copy(scope = Scope.Local)) + findDeclarations(name)
                else
                    findDeclarations(name)
            }
            Pair(listOf(headParam) + tailParams, headHints + tailHints)
        }
    }

    private fun List<Declaration.Function>.inferTypesMembers(
        findDeclarations: (String) -> List<Declaration>
    ): Pair<List<Declaration.Function>, TypeHints> {
        val result = map { it.inferTypesFunction(findDeclarations) }
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
    val errors = inferTypesErrorScan(result)

    return if (errors.isEmpty()) {
        Either.Some(result)
    } else {
        Either.Error(errors)
    }
}