package com.supersoftcafe.yafl.ast

data class Ast(val modules: List<Module>)
data class Module(
    val name: String,
    val variables: List<Variable>,
    val interfaces: List<Interface>,
    val klasses: List<Klass>,
    val structs: List<Struct>
)
data class Variable(val name: String)
data class Interface(val name: String)
data class Struct(val name: String)
data class Klass(val name: String)