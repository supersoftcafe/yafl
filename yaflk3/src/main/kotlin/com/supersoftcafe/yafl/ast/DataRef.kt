package com.supersoftcafe.yafl.ast

import com.supersoftcafe.yafl.utils.Namer

sealed class DataRef {
    abstract val name: String
    abstract val genericParameters: List<TypeRef>

    data class Resolved(
        override val name: String,
        val id: Namer,
        val scope: Scope,
        override val genericParameters: List<TypeRef> = listOf()
    ): DataRef()

    data class Unresolved(
        override val name: String,
        override val genericParameters: List<TypeRef> = listOf()
    ) : DataRef()
}
