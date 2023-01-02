package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Namer


private class ResolveTypesErrorScan(val globals: Map<Namer, Declaration>, val hints: TypeHints) {
    private fun TypeRef?.scan(sourceRef: SourceRef): List<String> {
        return when (this) {
            null, is TypeRef.Named, is TypeRef.Primitive, TypeRef.Unit ->
                listOf()

            is TypeRef.Unresolved ->
                listOf("$sourceRef unresolved type '$name'")

            is TypeRef.Tuple ->
                fields.flatMap { it.typeRef.scan(sourceRef) }

            is TypeRef.Callable ->
                result.scan(sourceRef) + parameter.scan(sourceRef)
        }
    }

    private fun Expression?.scan(): List<String> {
        return if (this == null) listOf()
        else typeRef.scan(sourceRef).ifEmpty {
            when (this) {
                is Expression.LoadMember -> base.scan()
                is Expression.If -> condition.scan() + ifTrue.scan() + ifFalse.scan()
                is Expression.Tuple -> fields.flatMap { it.expression.scan() }
                is Expression.Lambda -> body.scan() + parameters.flatMap { it.scan() }
                is Expression.NewKlass -> parameter.scan()
                is Expression.Llvmir -> inputs.flatMap { it.scan() }
                is Expression.Call -> callable.scan() + parameter.scan()
                else -> typeRef.scan(sourceRef)
            }
        }
    }

    private fun Declaration.Function.scanFunction(): List<String> {
        return sourceReturnType.scan(sourceRef).ifEmpty { returnType.scan(sourceRef) } +
                thisDeclaration.scan() +
                parameters.flatMap { it.scan() }
    }

    private fun Declaration.Let.scanLet(): List<String> {
        return sourceTypeRef.scan(sourceRef).ifEmpty { typeRef.scan(sourceRef) } +
                body.scan()
    }

    private fun Declaration.Alias.scanAlias(): List<String> {
        return typeRef.scan(sourceRef)
    }

    private fun Declaration.Klass.scanKlass(): List<String> {
        return parameters.flatMap { it.scanLet() } +
                members.flatMap { it.scanFunction() } +
                extends.flatMap { it.scan(sourceRef) }
    }

    private fun Declaration.scan(): List<String> {
        return when (this) {
            is Declaration.Function -> scanFunction()
            is Declaration.Let -> scanLet()
            is Declaration.Klass -> scanKlass()
            is Declaration.Alias -> scanAlias()
        }
    }

    fun scan(ast: Ast): List<String> {
        return ast.declarations.flatMap { (_, declaration, _) ->
            declaration.scan()
        }
    }
}


fun resolveTypesErrorScan(ast: Ast): List<String> {
    return ResolveTypesErrorScan(
        ast.declarations.associate { (_, declaration, _) -> declaration.id to declaration },
        ast.typeHints
    ).scan(ast)
}

