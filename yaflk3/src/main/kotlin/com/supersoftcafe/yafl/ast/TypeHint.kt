package com.supersoftcafe.yafl.ast

data class TypeHint(
    val inputTypeRef: TypeRef? = null,
    val outputTypeRef: TypeRef? = null
)
