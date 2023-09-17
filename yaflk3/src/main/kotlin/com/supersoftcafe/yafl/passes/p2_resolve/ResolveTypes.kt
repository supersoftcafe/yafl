package com.supersoftcafe.yafl.passes.p2_resolve

import com.supersoftcafe.yafl.models.ast.*
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.some


class ResolveTypes() {


    private fun DataRef.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): DataRef {
        return this
    }

    private fun TypeRef.Unresolved.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): TypeRef {
        // Find anything that matches the name and is a type declaration
        // If it's a user type, construct a reference to it
        // If it's an alias, take a copy of its target, if the target is not an alias...  no jumping around

        val found = findDeclarations(name)
            .filterIsInstance<Declaration.Type>()
            .filter { id == null || id == it.id }

        val declaration = found.singleOrNull()
        return if (declaration == null) {
            this

        } else if (declaration is Declaration.Klass) {
            val extends = declaration.extends.filterIsInstance<TypeRef.Klass>()
            if (extends.size != declaration.extends.size)
                this
            else
                TypeRef.Klass(declaration.name, declaration.id, extends)

        } else if (declaration is Declaration.Alias) {
            if (declaration.typeRef.resolved)
                declaration.typeRef
            else
                this

        } else {
            throw IllegalStateException("${declaration.javaClass.name} is not a supported type declaration")
        }
    }

    private fun TypeRef.Tuple.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): TypeRef.Tuple {
        return copy(fields = fields.map { field ->
            field.copy(typeRef = field.typeRef?.resolveTypes(sourceRef, findDeclarations) ?: field.typeRef)
        })
    }

    private fun TypeRef.TaggedValues.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): TypeRef.TaggedValues {
        return copy(tags = tags.map { tag ->
            tag.copy(typeRef = tag.typeRef.resolveTypes(sourceRef, findDeclarations))
        })
    }

    private fun TypeRef.Callable.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): TypeRef.Callable {
        return copy(
            parameter = parameter?.resolveTypes(sourceRef, findDeclarations),
            result = result?.resolveTypes(sourceRef, findDeclarations)
        )
    }

    private fun TypeRef.resolveTypes(
        sourceRef: SourceRef,
        findDeclarations: (String) -> List<Declaration>
    ): TypeRef {
        return when (this) {
            is TypeRef.Unresolved   -> resolveTypes(sourceRef, findDeclarations)
            is TypeRef.Tuple        -> resolveTypes(sourceRef, findDeclarations)
            is TypeRef.TaggedValues -> resolveTypes(sourceRef, findDeclarations)
            is TypeRef.Callable     -> resolveTypes(sourceRef, findDeclarations)
            is TypeRef.Primitive, is TypeRef.Klass -> this
        }
    }

    private fun WhenBranch.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): WhenBranch {
        return copy(
            parameter = parameter.resolveTypes(findDeclarations),
            expression = expression.resolveTypes(findDeclarations)
        )
    }

    private fun Expression.Tuple.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Expression.Tuple {
        return copy(
            typeRef = typeRef?.resolveTypes(sourceRef, findDeclarations),
            fields = fields.map { field ->
                field.copy(expression = field.expression.resolveTypes(findDeclarations))
            }
        )
    }

    private fun Expression.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Expression {
        return when (this) {
            is Expression.Float, is Expression.Integer ->
                this

            is Expression.RawPointer -> {
                copy(
                    field = field.resolveTypes(findDeclarations)
                )
            }

            is Expression.Characters -> {
                copy(
                    typeRef = typeRef.resolveTypes(sourceRef, findDeclarations)
                )
            }

            is Expression.Let -> {
                copy(
                    let = let.resolveTypes(findDeclarations),
                    tail = tail.resolveTypes { name ->
                        let.findByName(name) + findDeclarations(name)
                    }
                )
            }

            is Expression.Assert -> {
                copy(
                    value = value.resolveTypes(findDeclarations),
                    condition = condition.resolveTypes(findDeclarations)
                )
            }

            is Expression.ArrayLookup -> {
                copy(
                    array = array.resolveTypes(findDeclarations),
                    index = index.resolveTypes(findDeclarations)
                )
            }

            is Expression.NewKlass -> {
                copy(
                    typeRef = typeRef.resolveTypes(sourceRef, findDeclarations),
                    parameter = parameter.resolveTypes(findDeclarations)
                )
            }

            is Expression.Tag -> {
                copy(
                    typeRef = typeRef?.resolveTypes(sourceRef, findDeclarations),
                    value = value.resolveTypes(findDeclarations)
                )
            }

            is Expression.Call -> {
                copy(
                    typeRef = typeRef?.resolveTypes(sourceRef, findDeclarations),
                    callable = callable.resolveTypes(findDeclarations),
                    parameter = parameter.resolveTypes(findDeclarations)
                )
            }

            is Expression.Parallel -> {
                copy(
                    typeRef = typeRef?.resolveTypes(sourceRef, findDeclarations),
                    parameter = parameter.resolveTypes(findDeclarations)
                )
            }

            is Expression.Tuple -> resolveTypes(findDeclarations)

            is Expression.If -> {
                copy(
                    condition = condition.resolveTypes(findDeclarations),
                    ifTrue = ifTrue.resolveTypes(findDeclarations),
                    ifFalse = ifFalse.resolveTypes(findDeclarations)
                )
            }

            is Expression.When -> {
                copy(
                    typeRef = typeRef?.resolveTypes(sourceRef, findDeclarations),
                    condition = condition.resolveTypes(findDeclarations),
                    branches = branches.map { it.resolveTypes(findDeclarations) },
                )
            }

            is Expression.LoadMember -> {
                copy(
                    typeRef = typeRef?.resolveTypes(sourceRef, findDeclarations),
                    base = base.resolveTypes(findDeclarations)
                )
            }

            is Expression.LoadData -> {
                copy(
                    typeRef = typeRef?.resolveTypes(sourceRef, findDeclarations),
                    dataRef = dataRef.resolveTypes(sourceRef, findDeclarations)
                )
            }

            is Expression.Llvmir -> {
                copy(
                    typeRef = typeRef.resolveTypes(sourceRef, findDeclarations),
                    inputs = inputs.map { it.resolveTypes(findDeclarations) }
                )
            }

            is Expression.Lambda -> {
                copy(
                    typeRef = typeRef?.resolveTypes(sourceRef, findDeclarations),
                    body = body.resolveTypes(findDeclarations),
                    parameter = parameter.resolveTypes(findDeclarations)
                )
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



    private fun Declaration.Alias.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Declaration.Alias {
        return copy(
            typeRef = typeRef.resolveTypes(sourceRef, findDeclarations)
        )
    }

    private fun Declaration.Klass.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Declaration.Klass {
        val members = members.map { member ->
            member.resolveTypes { name ->
                findDeclarations(name) + parameters.filter { it.name == name } + members.filter { it.name == name }
            }
        }
        return copy(
            parameters = parameters.map { it.resolveTypes(findDeclarations) },
            members = members,
            extends = extends.resolveTypeRefs(sourceRef, findDeclarations)
        )
    }

    private fun Declaration.Let.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Declaration.Let {
        return copy(
            sourceTypeRef = sourceTypeRef?.resolveTypes(sourceRef, findDeclarations),
            typeRef = typeRef?.resolveTypes(sourceRef, findDeclarations),
            body = body?.resolveTypes(findDeclarations),
            dynamicArraySize = dynamicArraySize?.resolveTypes(findDeclarations),
            destructure = destructure.map { it.resolveTypes(findDeclarations) }
        )
    }

    private fun Declaration.Function.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Declaration.Function {
        return copy(
            body = body?.resolveTypes(findDeclarations),
            extensionType = extensionType?.resolveTypes(sourceRef, findDeclarations),
            sourceReturnType = sourceReturnType?.resolveTypes(sourceRef, findDeclarations),
            thisDeclaration = thisDeclaration.resolveTypes(findDeclarations),
            parameter = parameter.resolveTypes(findDeclarations),
        )
    }

    private fun Declaration.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Declaration {
        return when (this) {
            is Declaration.Alias   -> resolveTypes(findDeclarations)
            is Declaration.Klass   -> resolveTypes(findDeclarations)
            is Declaration.Let     -> resolveTypes(findDeclarations)
            is Declaration.Function-> resolveTypes(findDeclarations)
        }
    }

    fun Root.resolveTypes(
        findDeclarations: (String) -> List<Declaration>
    ): Root {
        return copy(
            declarations = declarations.map { it.resolveTypes(findDeclarations) }
        )
    }

    fun resolveTypes(ast: Ast): Ast {
        val result = ast.copy(declarations = ast.declarations.map {
            it.resolveTypes(ast.findDeclarations(it.imports))
        })

        return if (ast != result)
             resolveTypes(result)
        else result
    }
}
