package com.supersoftcafe.yafl.passes.p3_infer

import com.supersoftcafe.yafl.models.ast.*
import com.supersoftcafe.yafl.passes.p4_optimise.toSignature
import com.supersoftcafe.yafl.utils.*


class InferTypes(private val typeHints: TypeHints) {

    private fun Declaration.Let.searchByName(searchName: String): List<Declaration> {
        return if (name != searchName)
             destructure.flatMap { it.searchByName(searchName) }
        else listOf(this)
    }

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

                val first = found.singleOrNull()
                if (first == null)
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

    private fun Expression.If.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Expression.If, TypeHints> {
        val (conditionExpr, condHints) = condition.inferTypes(TypeRef.Bool, findDeclarations)
        val (ifFalseExpr, ifFalseHints) = ifFalse.inferTypes(receiver, findDeclarations)
        val (ifTrueExpr, ifTrueHints) = ifTrue.inferTypes(receiver, findDeclarations)

        // Put it all back together and derive a return type from the branches
        return Pair(copy(
            typeRef = mergeTypes(null, inputTypes = listOfNotNull(ifFalseExpr.typeRef, ifTrueExpr.typeRef)),
            ifTrue = ifTrueExpr, ifFalse = ifFalseExpr,
            condition = conditionExpr,
        ), condHints + ifFalseHints + ifTrueHints)
    }

    private fun WhenBranch.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
        tagsType: TypeRef.TaggedValues?
    ): Pair<WhenBranch, TypeHints> {
        return if (tag == null) {
            // Else branch
            val (expression, exprHints) = expression.inferTypes(receiver, findDeclarations)
            tupleOf(copy(expression = expression), exprHints)
        } else {
            val tagType = tagsType?.tags?.firstOrNull { it.name == tag }
            if (tagType == null) {
                // Unknown tag so can't do much
                tupleOf(this, typeHintsOf())
            } else {
                val (parameter, paramHints) = parameter.inferTypesLet(tagType.typeRef, findDeclarations)
                val (expression, exprHints) = expression.inferTypes(receiver, findDeclarations)
                tupleOf(copy(
                    parameter = parameter,
                    expression = expression
                ), exprHints + paramHints)
            }
        }
    }

    private fun List<WhenBranch>.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
        tagsType: TypeRef.TaggedValues?
    ): Pair<List<WhenBranch>, TypeHints> {
        val result = map { it.inferTypes(receiver, findDeclarations, tagsType) }
        return tupleOf(result.map { it.first }, result.fold(typeHintsOf()) { l, r -> l + r.second })
    }

    private fun Expression.When.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Expression.When, TypeHints> {
        // Infer types for the expression that should give us a tagged instance
        val (condition, enumHints) = condition.inferTypes(null, findDeclarations)

        // For each branch infer types
        val (branches, branchesHints) = branches.inferTypes(
            receiver, findDeclarations, condition.typeRef as? TypeRef.TaggedValues)

        // Put it all back together and derive a return type from the branches
        return Pair(copy(
            typeRef = mergeTypes(null, inputTypes = branches.mapNotNull { it.expression.typeRef }),
            condition = condition,
            branches = branches
        ), enumHints + branchesHints)
    }

    private fun Expression.LoadMember.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Expression.LoadMember, TypeHints> {
        val (base, baseHints) = base.inferTypes(null, findDeclarations)

        return when (val baseTypeRef = base.typeRef) {
            is TypeRef.Klass ->
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

                            val resultTypeRef = if (entry.typeRef?.complete == true)
                                entry.typeRef
                            else typeRef

                            Pair(copy(
                                base = base,
                                typeRef = resultTypeRef,
                                id = entry.id
                            ), baseHints + entryHint)
                        }
                    }

                    else -> null
                }

            else -> null
        } ?: Pair(copy(base = base), baseHints)
    }

    private fun Expression.LoadData.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Expression, TypeHints> {
        val (newDataRef, declaration) = dataRef.resolveData(sourceRef, receiver, findDeclarations)
        return if (declaration != null && declaration.scope is Scope.Member) {
            Pair(
                Expression.LoadMember(
                    sourceRef, typeRef,
                    Expression.LoadData(
                        sourceRef, null,
                        com.supersoftcafe.yafl.models.ast.DataRef.Unresolved("this"),
                    ),
                    declaration.name,
                    declaration.id,
                ), emptyTypeHints()
            )
        } else {
            val parsedType = declaration?.sourceTypeRef
            val inputType = declaration?.typeRef

            val newTypeRef = mergeTypes(parsedType, inputType, receiver)

            val hints = if (declaration == null || newTypeRef == null) emptyTypeHints()
            else typeHintsOf(declaration.id to TypeHint(outputTypeRef = newTypeRef))

            Pair(copy(
                dataRef = newDataRef,
                typeRef = newTypeRef
            ), hints)
        }
    }

    private fun Expression.Lambda.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Expression.Lambda, TypeHints> {
        val typeRef = mergeTypes(
            inputType = TypeRef.Callable(parameter.typeRef, body.typeRef),
            outputType = receiver)

        val (parameter, paramHints) = parameter.inferTypesLet(
            (receiver as? TypeRef.Callable)?.parameter,
            findDeclarations)
        val (body, bodyHints) = body.inferTypes((typeRef as? TypeRef.Callable)?.result) { name ->
            parameter.findByName(name) + findDeclarations(name)
        }

        return Pair(copy(
            body = body,
            typeRef = typeRef,
            parameter = parameter
        ), paramHints + bodyHints)
    }

    private fun Expression.Tag.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Expression.Tag, TypeHints> {
        val receiver = receiver as? TypeRef.TaggedValues
        val tagRecvr = receiver?.tags?.firstOrNull { it.name == tag }
        val (value, valueHints) = value.inferTypes(tagRecvr?.typeRef, findDeclarations)
        val valueTypeRef = value.typeRef as? TypeRef.Tuple

        val typeRef = if (valueTypeRef == null)
            null
        else if (receiver == null)
            TypeRef.TaggedValues(tags = listOf(TagTypeField(valueTypeRef, tag)))
        else if (tagRecvr == null)
            receiver.copy(tags = (receiver.tags + TagTypeField(typeRef = valueTypeRef, tag)).sortedBy { it.name })
        else
            receiver.copy(tags = receiver.tags.map { if (it.name == tag) it.copy(typeRef = valueTypeRef) else it })

        return tupleOf(copy(
            typeRef = typeRef,
            value = value
        ), valueHints)
    }

    private fun Expression.NewKlass.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Expression.NewKlass, TypeHints> {

        val typeRef = typeRef as TypeRef.Klass

        val declaration = findDeclarations(typeRef.name).single { it.id == typeRef.id } as Declaration.Klass

        val (parameter, paramHints) = parameter.inferTypes(TypeRef.Tuple(declaration.parameters.map {
            val paramTypeRef = it.typeRef

            TupleTypeField(if (it.arraySize != null) {
                // Array requires a lambda parameter
                TypeRef.Callable(TypeRef.Tuple(listOf(TupleTypeField(TypeRef.Int32, null))), paramTypeRef)
            } else {
                // Otherwise just the value
                paramTypeRef
            }, it.name)
        }), findDeclarations)

        val hints = (parameter.typeRef as? TypeRef.Tuple)?.fields
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

        return tupleOf(copy(
            parameter = parameter
        ), hints?.fold(paramHints, TypeHints::plus) ?: paramHints)
    }

    private fun Expression?.inferTypesNullable(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
    ): Pair<Expression?, TypeHints> {
        val pair = this?.inferTypes(receiver, findDeclarations)
        return Pair(pair?.first, pair?.second ?: typeHintsOf())
    }

    private fun Expression.inferTypes(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>,
    ): Pair<Expression, TypeHints> {
        return when (this) {
            is Expression.RawPointer -> {
                val (field, fieldHints) = field.inferTypes(null, findDeclarations)
                Pair(copy(field = field), fieldHints)
            }

            is Expression.Let -> {
                val (let, letHints) = let.inferTypesLet(receiver, findDeclarations)
                val (tail, tailHints) = tail.inferTypes(receiver) { name ->
                    let.findByName(name) + findDeclarations(name)
                }
                Pair(copy(let = let, tail = tail, typeRef = tail.typeRef), letHints + tailHints)
            }

            is Expression.Assert -> {
                val (value, valueHints) = value.inferTypes(receiver, findDeclarations)
                val (condition, conditionHints) = condition.inferTypes(TypeRef.Bool, findDeclarations)
                Pair(copy(value = value, condition = condition, typeRef = value.typeRef), valueHints + conditionHints)
            }

            is Expression.ArrayLookup -> {
                val (array, arrayHints) = array.inferTypes(receiver, findDeclarations)
                val (index, indexHints) = index.inferTypes(TypeRef.Int32, findDeclarations)
                Pair(copy(array = array, index = index, typeRef = array.typeRef), arrayHints + indexHints)
            }

            is Expression.Float, is Expression.Integer, is Expression.Characters -> {
                Pair(this, emptyTypeHints())
            }

            is Expression.Tag -> inferTypes(receiver, findDeclarations)

            is Expression.NewKlass -> inferTypes(receiver, findDeclarations)

            is Expression.LoadMember -> inferTypes(receiver, findDeclarations)

            is Expression.Llvmir -> {
                val newInputs = inputs.map { it.inferTypes(null, findDeclarations) }
                val hints = newInputs.fold(emptyTypeHints()) { acc, (expr, hints) -> acc + hints }
                Pair(copy(
                    inputs = newInputs.map { (expr, hints) -> expr }
                ), hints)
            }

            is Expression.LoadData -> inferTypes(receiver, findDeclarations)

            is Expression.Lambda -> inferTypes(receiver, findDeclarations)

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
                    callable = newCallable,
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

            is Expression.If -> inferTypes(receiver, findDeclarations)

            is Expression.When -> inferTypes(receiver, findDeclarations)
        }
    }

    private fun List<Declaration.Let>.inferTypesLetList(
        receivers: List<TypeRef?>,
        findDeclarations: (String) -> List<Declaration>
    ): Pair<List<Declaration.Let>, TypeHints> {
        // Default expressions and array size expressions can see parameters to the left. That's what makes it
        // different to inferTypesMembers, which can see all members simultaneously. Parameters can't see to the
        // right. This is true for both class and function parameters.

        return if (isEmpty()) {
            Pair(listOf(), emptyTypeHints())
        } else {
            val (headParam, headHints) = first().inferTypesLet(receivers.firstOrNull(), findDeclarations)
            val (tailParams, tailHints) = drop(1).inferTypesLetList(receivers.drop(1)) { name ->
                if (name == headParam.name)
                     // Change scope to local for klass due to its duality as a member and a local
                     listOf(headParam.copy(scope = Scope.Local)) + findDeclarations(name)
                else findDeclarations(name)
            }
            Pair(listOf(headParam) + tailParams, headHints + tailHints)
        }
    }

    private fun List<Declaration.Let>.toSourceTupleTypeRef(): TypeRef.Tuple {
        return TypeRef.Tuple(
            fields = map { TupleTypeField(it.sourceTypeRef, it.name) }
        )
    }

    private fun List<Declaration.Let>.toTupleTypeRef(): TypeRef.Tuple {
        return TypeRef.Tuple(
            fields = map { TupleTypeField(it.typeRef, it.name) }
        )
    }

    private fun Declaration.Let.inferTypesLet(
        receiver: TypeRef?,
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Declaration.Let, TypeHints> {
        val typeRef = mergeTypes(
            if (destructure.isEmpty()) sourceTypeRef else destructure.toSourceTupleTypeRef(),
            inputTypes  = typeHints.getInputTypeRefs( id) + listOfNotNull(body?.typeRef),
            outputTypes = typeHints.getOutputTypeRefs(id),
        )

        val (body, typeHints) = body.inferTypesNullable(typeRef, findDeclarations)
        val (dynamicArraySize, dynamicArraySizeHints) = dynamicArraySize.inferTypesNullable(TypeRef.Int32, findDeclarations)
        var (destructure, destrHints) = destructure.inferTypesLetList(
            (receiver as? TypeRef.Tuple)?.fields?.map { it.typeRef } ?: listOf(),
            findDeclarations)

        return Pair(copy(
            destructure = destructure,
            dynamicArraySize = dynamicArraySize,
            signature = typeRef.toSignature(name),
            typeRef = typeRef,
            body = body
        ), typeHints + dynamicArraySizeHints + destrHints)
    }

    private fun Declaration.Let.getPerParamTypeHints(
        typeRef: TypeRef?
    ): List<Pair<Namer, TypeHint>> {
        return if (destructure.isEmpty()) {
            // This is a concrete declaration so build a hint
            listOf(tupleOf(id, TypeHint(inputTypeRef = typeRef)))
        } else if (typeRef is TypeRef.Tuple) {
            // Follow the destructure tree and the tuple type to find more type hints
            destructure.zip(typeRef.fields).flatMap { (let, fieldType) ->
                let.getPerParamTypeHints(fieldType.typeRef)
            }
        } else {
            // Doesn't add up so give up
            listOf()
        }
    }

    private fun Declaration.Function.inferTypesFunction(
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Declaration.Function, TypeHints> {
        // Return type is derived from body only
        // Type hints can only impact parameters

        // Get the type hints for this function, treating it as a variable with a lambda
        val filtered = typeHints.getOutputTypeRefs(id)

        // Figure out individual parameter hints from the function hint
        val paramHints = typeHintsOf(filtered.filterIsInstance<TypeRef.Callable>().flatMap { typeRef ->
            parameter.getPerParamTypeHints(typeRef.parameter)
        })

        val (bodyExpr, bodyHints) = body.inferTypesNullable(sourceReturnType ?: returnType) { name ->
            thisDeclaration.searchByName(name) + parameter.searchByName(name) + findDeclarations(name)
        }

        val (param, paramHints2) = parameter.inferTypesLet(null, findDeclarations)

        return Pair(copy(
            parameter = param,
            returnType = sourceReturnType ?: bodyExpr?.typeRef,
            body = bodyExpr,
        ), bodyHints + paramHints + paramHints2)
    }


    private fun Declaration.Klass.findMembers(
        name: String,
        findDeclarations: (String) -> List<Declaration>
    ): List<Declaration> {
        return ((parameters + members).filter { it.name == name } + extends.flatMap { typeRef ->
            if (typeRef is TypeRef.Klass)
                (findDeclarations(typeRef.name).first { it.id == typeRef.id } as Declaration.Klass)
                    .findMembers(name, findDeclarations)
            else
                listOf()
        }).distinctBy { // Remove duplicates due to diamond inheritance
            it.id
        }.distinctBy { // Only closest example of fully resolved function is used, if known
            (it as Declaration.Data).signature ?: it.id.toString()
        }
    }

    private fun Declaration.Klass.inferTypesKlass(
        findDeclarations: (String) -> List<Declaration>
    ): Pair<Declaration.Klass, TypeHints> {
        // Parameters can only see other parameters to the left of their position
        val (parameters, parametersHints) = parameters.inferTypesLetList(listOf(), findDeclarations)

        // Members can see all parameters and all members
        val (members, membersHints) = members.inferTypesMembers { name ->
            findMembers(name, findDeclarations) + findDeclarations(name)
        }

        return Pair(copy(
            members = members,
            parameters = parameters
        ), membersHints + parametersHints)
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
                inferTypesLet(null, findDeclarations)

            is Declaration.Function ->
                inferTypesFunction(findDeclarations)

            is Declaration.Klass ->
                inferTypesKlass(findDeclarations)

            is Declaration.Alias ->
                // In theory nothing references the alias declarations after the "resolveTypes" stage
                throw IllegalStateException("alias shouldn't exist here")
        }
    }

    fun inferTypesInternal(ast: Ast): Ast {
        val result = ast.declarations.map { (imports, declarations, file) ->
            Pair(Root(imports, declarations.map { declaration ->
                val (declaration, typeHints) = declaration.inferTypes(ast.findDeclarations(imports))
                declaration
            }, file), typeHints)
        }

        return ast.copy(
            declarations = result.map { it.first },
            typeHints = result.fold(TypeHints()) { acc, value ->
                acc + value.second
            }
        )
    }
}

fun inferTypes2(ast: Ast): Ast {
    val result = InferTypes(ast.typeHints).inferTypesInternal(ast)
    return if (ast != result)
         inferTypes2(result)
    else result
}