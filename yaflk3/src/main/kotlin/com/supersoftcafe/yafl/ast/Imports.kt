package com.supersoftcafe.yafl.ast

data class Imports(val paths: List<String>)
private val EMPTY: Imports = Imports(listOf())

fun importsOf(paths: List<String>) = Imports(paths)
fun importsOf(vararg paths: String) = Imports(listOf(*paths))
fun importsOf() = EMPTY
