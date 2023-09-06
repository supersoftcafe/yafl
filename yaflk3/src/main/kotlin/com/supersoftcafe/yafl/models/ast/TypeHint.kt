package com.supersoftcafe.yafl.models.ast

data class TypeHint(
    val inputTypeRef: TypeRef? = null,
    val outputTypeRef: TypeRef? = null
)
