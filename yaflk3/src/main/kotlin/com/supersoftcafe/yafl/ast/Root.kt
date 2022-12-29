package com.supersoftcafe.yafl.ast

data class Root(
    val imports: Imports,
    val declaration: Declaration,
    val file: String,
) {
    override fun toString() = declaration.toString()
}
