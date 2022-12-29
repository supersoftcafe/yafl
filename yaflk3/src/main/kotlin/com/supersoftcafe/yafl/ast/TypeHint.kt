package com.supersoftcafe.yafl.ast

data class TypeHint(
    val sourceRef: SourceRef,
    val inputTypeRef: TypeRef? = null,
    val outputTypeRef: TypeRef? = null
)
