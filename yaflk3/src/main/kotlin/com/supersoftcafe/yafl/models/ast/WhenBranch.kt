package com.supersoftcafe.yafl.models.ast

data class WhenBranch(
    val tag: String?,
    val parameter: Declaration.Let,
    val expression: Expression
)
