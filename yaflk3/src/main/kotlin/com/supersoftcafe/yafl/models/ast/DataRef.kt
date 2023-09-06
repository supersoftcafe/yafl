package com.supersoftcafe.yafl.models.ast

import com.supersoftcafe.yafl.utils.Namer

sealed class DataRef {
    abstract val name: String

    data class Resolved(
        override val name: String,
        val id: Namer,
        val scope: Scope,
    ): DataRef()

    data class Unresolved(
        override val name: String,
    ) : DataRef()
}
