package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Either

class ResolveTypes() {

    private fun Declaration.Alias.targetTypeRefWithModifiedGenerics(
        genericParams: List<TypeRef>
    ): TypeRef {
        assert(genericDeclaration.size == genericParams.size)

        val genericSubstitutionById = genericDeclaration.zip(genericParams)
            .associate { (declaration, target) -> declaration.id to target }

        fun TypeRef.updateWithGenerics(): TypeRef = when (this) {
            is TypeRef.Callable -> copy(parameter?.updateWithGenerics() as? TypeRef.Tuple, result?.updateWithGenerics())
            is TypeRef.Tuple -> copy(fields = fields.map { it.copy(typeRef = it.typeRef?.updateWithGenerics()) })
            is TypeRef.Generic -> genericSubstitutionById[id] ?: this
            is TypeRef.Klass, is TypeRef.Primitive, is TypeRef.Unresolved, TypeRef.Unit -> this
        }

        return typeRef.updateWithGenerics()
    }

    private fun DataRef?.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): DataRef? {
        return when (this) {
            is DataRef.Unresolved -> {
                copy(genericParameters = genericParameters.map {
                    it.resolveTypes(sourceRef, findDeclarations)!!
                })
            }

            is DataRef.Resolved -> {
                copy(genericParameters = genericParameters.map {
                    it.resolveTypes(sourceRef, findDeclarations)!!
                })
            }

            null -> {
                null
            }
        }
    }

    private fun TypeRef?.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): TypeRef? {
        return when (this) {
            is TypeRef.Unresolved -> {
                // Only proceed if generic params are resolved
                val resolvedGenericParams = genericParameters.map {
                    it.resolveTypes(sourceRef, findDeclarations) ?: it
                }

                if (resolvedGenericParams.any { !it.resolved }) {
                    // Not all generic params are resolved yet
                    copy(genericParameters = resolvedGenericParams)

                } else {
                    // Find anything that matches the name and is a type declaration
                    // If it's a user type, construct a reference to it
                    // If it's an alias, take a copy of its target, if the target is not an alias...  no jumping around

                    val found = findDeclarations(name)
                        .filterIsInstance<Declaration.Type>()
                        .filter { (id == null || id == it.id) && it.genericDeclaration.size == genericParameters.size }

                    val declaration = found.singleOrNull()
                    if (declaration == null) {
                        copy(genericParameters = resolvedGenericParams)

                    } else if (declaration is Declaration.Klass) {
                        val extends = declaration.extends.filterIsInstance<TypeRef.Klass>()
                        if (extends.size != declaration.extends.size)
                            copy(genericParameters = resolvedGenericParams)
                        else
                            TypeRef.Klass(declaration.name, declaration.id, extends, resolvedGenericParams)

                    } else if (declaration is Declaration.Alias) {
                        if (declaration.typeRef.resolved)
                            declaration.targetTypeRefWithModifiedGenerics(resolvedGenericParams)
                        else
                            copy(genericParameters = resolvedGenericParams)

                    } else if (declaration is Declaration.Generic) {
                        TypeRef.Generic(declaration.name, declaration.id)

                    } else {
                        throw IllegalStateException("${declaration.javaClass.name} is not a supported type declaration")
                    }
                }
            }

            is TypeRef.Tuple ->
                copy(fields = fields.map { field ->
                    field.copy(typeRef = field.typeRef?.resolveTypes(sourceRef, findDeclarations) ?: field.typeRef)
                })

            is TypeRef.Callable -> {
                val p = parameter.resolveTypes(sourceRef, findDeclarations)
                val r = result?.resolveTypes(sourceRef, findDeclarations)
                copy(parameter = p as TypeRef.Tuple, result = r)
            }

            null, TypeRef.Unit, is TypeRef.Primitive, is TypeRef.Klass, is TypeRef.Generic ->
                this
        }
    }

    private fun Expression?.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Expression? {
        return when (this) {
            null, is Expression.Float, is Expression.Integer ->
                this

            is Expression.RawPointer -> {
                val f = field.resolveTypes(findDeclarations)!!
                copy(field = f)
            }

            is Expression.Characters -> {
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)!!
                copy(typeRef = t)
            }

            is Expression.Let -> {
                val l = let.resolveTypes(findDeclarations) as Declaration.Let
                val t = tail.resolveTypes(findDeclarations)!!
                copy(let = l, tail = t)
            }

            is Expression.Assert -> {
                val v = value.resolveTypes(findDeclarations)!!
                val c = condition.resolveTypes(findDeclarations)!!
                copy(value = v, condition = c)
            }

            is Expression.ArrayLookup -> {
                val a = array.resolveTypes(findDeclarations)!!
                val i = index.resolveTypes(findDeclarations)!!
                copy(array = a, index = i)
            }

            is Expression.NewKlass -> {
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)!!
                val p = parameter.resolveTypes(findDeclarations)
                copy(typeRef = t, parameter = p as Expression.Tuple)
            }

            is Expression.Call -> {
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)
                val c = callable.resolveTypes(findDeclarations)!!
                val p = parameter.resolveTypes(findDeclarations)
                copy(typeRef = t, callable = c, parameter = p as Expression.Tuple)
            }

            is Expression.Parallel -> {
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)
                val p = parameter.resolveTypes(findDeclarations)
                copy(typeRef = t, parameter = p as Expression.Tuple)
            }

            is Expression.Tuple -> {
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)
                val f = fields.map { field ->
                    field.copy(expression = field.expression.resolveTypes(findDeclarations)!!)
                }
                copy(typeRef = t, fields = f)
            }

            is Expression.If -> {
                val c = condition.resolveTypes(findDeclarations)!!
                val t = ifTrue.resolveTypes(findDeclarations)!!
                val f = ifFalse.resolveTypes(findDeclarations)!!
                copy(condition = c, ifTrue = t, ifFalse = f)
            }

            is Expression.LoadMember -> {
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)
                val b = base.resolveTypes(findDeclarations)!!
                copy(typeRef = t, base = b)
            }

            is Expression.LoadData -> {
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)
                val d = dataRef.resolveTypes(sourceRef, findDeclarations)!!
                copy(typeRef = t, dataRef = d)
            }

            is Expression.Llvmir -> {
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)!!
                val i = inputs.map { it.resolveTypes(findDeclarations)!! }
                copy(typeRef = t, inputs = i)
            }

            is Expression.Lambda -> {
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)
                val b = body.resolveTypes(findDeclarations)!!
                val p = parameters.map { it.resolveTypes(findDeclarations) as Declaration.Let }
                copy(typeRef = t, body = b, parameters = p)
            }
        }
    }

    private fun List<TypeRef>.resolveTypeRefs(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): List<TypeRef> {
        return mapNotNull { it.resolveTypes(sourceRef, findDeclarations) }
    }

    private fun List<Declaration>.resolveDeclarations(
        findDeclarations: (String) -> List<Declaration>
    ): List<Declaration> {
        return map { it.resolveTypes(findDeclarations) }
    }

    private fun Declaration.resolveTypes(
        findDeclarationsX: (String) -> List<Declaration>
    ): Declaration {
        val findDeclarations: (String) -> List<Declaration> = { name ->
            findDeclarationsX(name) + genericDeclaration.filter { it.name == name }
        }

        return when (this) {
            is Declaration.Generic -> {
                this
            }

            is Declaration.Alias -> {
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)
                copy(typeRef = t!!)
            }

            is Declaration.Klass -> {
                val p = parameters.resolveDeclarations(findDeclarations)
                val m = members.resolveDeclarations { name ->
                    findDeclarations(name) + parameters.filter { it.name == name } + members.filter { it.name == name }
                }
                val e = extends.resolveTypeRefs(sourceRef, findDeclarations)
                copy(
                    parameters = p.filterIsInstance<Declaration.Let>(),
                    members = m.filterIsInstance<Declaration.Function>(),
                    extends = e
                )
            }

            is Declaration.Let -> {
                val d = dynamicArraySize.resolveTypes(findDeclarations)
                val s = sourceTypeRef.resolveTypes(sourceRef, findDeclarations)
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)
                val b = body.resolveTypes(findDeclarations)
                copy(sourceTypeRef = s, typeRef = t, body = b, dynamicArraySize = d)
            }

            is Declaration.Function -> {
                val t = thisDeclaration.resolveTypes(findDeclarations)
                val p = parameters.resolveDeclarations(findDeclarations)
                val b = body.resolveTypes(findDeclarations)
                val r = sourceReturnType.resolveTypes(sourceRef, findDeclarations)
                val e = extensionType.resolveTypes(sourceRef, findDeclarations)

                copy(
                    body = b,
                    extensionType = e,
                    sourceReturnType = r,
                    thisDeclaration = t as Declaration.Let,
                    parameters = p.filterIsInstance<Declaration.Let>(),
                )
            }
        }
    }

    fun resolveTypes(ast: Ast): Ast {
        val result = ast.copy(declarations = ast.declarations.map { (imports, declaration, file) ->
            val declaration = declaration.resolveTypes(ast.findDeclarations(imports))
            Root(imports, declaration, file)
        })

        return if (ast != result)
             resolveTypes(result)
        else result
    }
}

fun resolveTypes(ast: Ast): Either<Ast, List<String>> {
    val result = ResolveTypes().resolveTypes(ast)
    val errors = resolveTypesErrorScan(result)

    return if (errors.isEmpty())
         Either.Some(result)
    else Either.Error(errors)
}