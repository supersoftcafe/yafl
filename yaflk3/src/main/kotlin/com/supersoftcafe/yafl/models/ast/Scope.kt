package com.supersoftcafe.yafl.models.ast

import com.supersoftcafe.yafl.utils.Namer

sealed class Scope {
    object Global : Scope()
    data class Member(val id: Namer, val level: Int) : Scope()
    object Local : Scope()
}
