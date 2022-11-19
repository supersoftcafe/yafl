package com.supersoftcafe.yafl.ast

data class Ast(
    val counter: Long = 0,
    val declarations: List<Root> = listOf(),
    val typeHints: TypeHints = TypeHints()
) {
    fun findDeclarations(imports: Imports, name: String): List<Declaration> {
        val names = imports.paths.map { if (it.isEmpty() || name.contains("::")) name else "$it::$name" }
        return declarations.map { it.declaration }.filter { it.name in names }
    }

    fun findDeclarations(imports: Imports): (String)->List<Declaration> {
        return { name -> findDeclarations(imports, name) }
    }
}
