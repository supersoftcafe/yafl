package com.supersoftcafe.yafl.models.ast

data class Ast(
    val declarations: List<Root> = listOf(),
    val typeHints: TypeHints = TypeHints()
) {
    fun findDeclarations(imports: Imports, name: String): List<Declaration> {
        val names = imports.paths.map { if (it.isEmpty() || name.contains("::")) name else "$it::$name" }
        return declarations.flatMap { it.declarations }.filter { it.name in names }
    }

    fun findDeclarations(imports: Imports): (String)->List<Declaration> {
        return { name -> findDeclarations(imports, name) }
    }

    operator fun plus(other: Ast): Ast {
        return Ast(declarations = declarations + other.declarations, typeHints = typeHints + other.typeHints)
    }
}
