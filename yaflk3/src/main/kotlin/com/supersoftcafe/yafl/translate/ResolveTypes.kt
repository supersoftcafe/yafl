package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Either

class ResolveTypes() {

    private fun TypeRef?.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): TypeRef? {
        return when (this) {
            is TypeRef.Unresolved -> {
                // Find anything that matches the name and is a type declaration
                // If it's a user type, construct a reference to it
                // If it's an alias, take a copy of its target, if the target is not an alias...  no jumping around

                val found = findDeclarations(name)
                    .filterIsInstance<Declaration.Type>()
                    .filter { (id == null || id == it.id) }

                val first = found.firstOrNull()
                if (first == null || found.size > 1) {
                    this
                } else if (first is Declaration.Klass) {
                    val extends = first.extends.filterIsInstance<TypeRef.Named>()
                    if (extends.size != first.extends.size) {
                        this
                    } else {
                        TypeRef.Named(first.name, first.id, extends)
                    }
                } else if (first is Declaration.Alias) {
                    if (first.typeRef.resolved)
                        first.typeRef
                    else
                        this
                } else {
                    throw IllegalStateException("${first.javaClass.name} is not a supported type declaration")
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

            null, TypeRef.Unit, is TypeRef.Primitive, is TypeRef.Named ->
                this
        }
    }

    private fun Expression?.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Expression? {
        return when (this) {
            null, is Expression.Float, is Expression.Integer, is Expression.Characters ->
                this

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
                copy(typeRef = t)
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
        findDeclarations: (String) -> List<Declaration>
    ): Declaration {
        return when (this) {
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
                val s = sourceTypeRef.resolveTypes(sourceRef, findDeclarations)
                val t = typeRef.resolveTypes(sourceRef, findDeclarations)
                val b = body.resolveTypes(findDeclarations)
                copy(sourceTypeRef = s, typeRef = t, body = b)
            }

            is Declaration.Function -> {
                val t = thisDeclaration.resolveTypes(findDeclarations)
                val p = parameters.resolveDeclarations(findDeclarations)
                val b = body.resolveTypes(findDeclarations)
                val r = sourceReturnType.resolveTypes(sourceRef, findDeclarations)

                copy(
                    thisDeclaration = t as Declaration.Let,
                    body = b,
                    parameters = p.filterIsInstance<Declaration.Let>(),
                    sourceReturnType = r
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