package com.supersoftcafe.yafl.ast

data class FunctionPrototype(val name: String, val typeRef: TypeRef.Callable, val defaultBody: Expression?)
