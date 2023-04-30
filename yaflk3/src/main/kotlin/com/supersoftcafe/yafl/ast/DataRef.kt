package com.supersoftcafe.yafl.ast

import com.supersoftcafe.yafl.utils.Namer

sealed class DataRef {
    data class Resolved(val name: String, val id: Namer, val scope: Scope, val genericParameters: List<TypeRef> = listOf()): DataRef()
    data class Unresolved(val name: String, val genericParameters: List<TypeRef> = listOf()) : DataRef()
}
