package com.supersoftcafe.yafl.models.ast

data class EnumEntry(
    val name: String,
    val parameters: List<Declaration.Let>
)