package com.supersoftcafe.yafl.ast

//sealed class TupleField {
//    abstract val expression: Expression
//
//    data class Named(override val expression: Expression, val name: String) : TupleField()
//    data class Indexed(override val expression: Expression, val index: Int, val unpack: Boolean) : TupleField()
//}

data class TupleExpressionField(val unpack: Boolean, val name: String?, val expression: Expression)