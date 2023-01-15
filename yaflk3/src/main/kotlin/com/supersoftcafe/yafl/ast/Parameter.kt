package com.supersoftcafe.yafl.ast

//sealed class Parameter {
//    abstract val typeRef: TypeRef?
//    abstract val names: Set<String>
//
//    data class Tuple(override val typeRef: TypeRef?, val fields: List<Parameter>) : Parameter() {
//        override val names = fields.flatMap { it.names }.toSet()
//    }
//
//    data class Value(override val typeRef: TypeRef?, val name: String, val default: Expression?) : Parameter() {
//        override val names = setOf(name)
//    }
//}