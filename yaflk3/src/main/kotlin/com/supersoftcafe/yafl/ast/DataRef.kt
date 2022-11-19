package com.supersoftcafe.yafl.ast

sealed class DataRef {
    data class Local(val name: String, val id: Long) : DataRef()
    data class Global(val name: String, val id: Long): DataRef()
    data class Unresolved(val name: String) : DataRef()
}
