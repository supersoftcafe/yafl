package com.supersoftcafe.yafl.models.ast

data class Root(
    val imports: Imports,
    val declarations: List<Declaration>,
    val file: String,
) {
    override fun toString() = declarations.joinToString()
}
