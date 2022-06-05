package com.supersoftcafe.yaflc

import kotlinx.collections.immutable.PersistentList
import kotlinx.collections.immutable.persistentListOf

sealed class Result<out TValue> {

    data class Ok<TValue>(val value: TValue, val sourceRef: SourceRef, val tokens: Tokens) : Result<TValue>()

    data class Absent<TValue>(val sourceRef: SourceRef) : Result<TValue>() {
        fun <TOut> xfer(): Result<TOut> = Absent(sourceRef)
        fun <TOut> toFail(message: String) = Fail<TOut>(sourceRef, message)
    }

    data class Fail<TValue>(val error: PersistentList<Pair<SourceRef, String>>) : Result<TValue>() {
        constructor(sourceRef: SourceRef, message: String) : this(persistentListOf(sourceRef to message))
        fun <TOut> xfer(): Result<TOut> = Fail(error)
    }


    fun <TOut> map(lambda: (SourceRef, TValue) -> TOut): Result<TOut> {
        return when (this) {
            is Ok -> Ok(lambda(sourceRef, value), sourceRef, tokens)
            is Fail -> xfer()
            is Absent -> xfer()
        }
    }

    fun peek(action: (TValue) -> Unit): Result<TValue> {
        if (this is Ok)
            action(this.value)
        return this
    }
}