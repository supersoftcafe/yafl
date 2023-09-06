package com.supersoftcafe.yafl.passes.p2_resolve

import com.supersoftcafe.yafl.models.ast.*
import com.supersoftcafe.yafl.passes.AbstractScanner
import com.supersoftcafe.yafl.utils.Namer


private class ResolveTypesErrorScan(val globals: Map<Namer, Declaration>, val hints: TypeHints) : AbstractScanner<String>() {
    override fun scanSource(self: TypeRef?, sourceRef: SourceRef): List<String> {
        return when (self) {
            null, is TypeRef.Klass, is TypeRef.Enum, is TypeRef.Primitive, TypeRef.Unit ->
                listOf()

            is TypeRef.Unresolved ->
                listOf("$sourceRef unresolved type '${self.name}'")

            is TypeRef.Tuple ->
                self.fields.flatMap { scanSource(it.typeRef, sourceRef) }

            is TypeRef.Callable ->
                scanSource(self.result, sourceRef) + scanSource(self.parameter, sourceRef)
        }
    }

    override fun scan(self: TypeRef?, sourceRef: SourceRef): List<String> {
        return scanSource(self, sourceRef)
    }
}


fun resolveTypesErrorScan(ast: Ast): List<String> {
    return ResolveTypesErrorScan(
        ast.declarations.flatMap { it.declarations }.associateBy { it.id },
        ast.typeHints
    ).scan(ast)
}
