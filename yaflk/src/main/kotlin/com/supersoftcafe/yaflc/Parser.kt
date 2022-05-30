package com.supersoftcafe.yaflc

import kotlinx.collections.immutable.PersistentList
import kotlinx.collections.immutable.persistentListOf


typealias Parser<TValue> = Tokens.() -> Result<TValue>


fun <TValue, TResult> Parser<TValue>.map(lambda: (SourceRef, TValue) -> TResult): Parser<TResult> {
    return { this@map().map(lambda) }
}

fun <TValue, TOut> Result<TValue>.mapResult(lambda: (Result.Ok<TValue>) -> Result<TOut>): Result<TOut> {
    return when (this) {
        is Result.Ok -> lambda(this)
        is Result.Fail -> xfer()
        is Result.Absent -> xfer()
    }
}

fun <TValue, TResult> Parser<TValue>.mapResult(lambda: (Result.Ok<TValue>) -> Result<TResult>): Parser<TResult> {
    return { this@mapResult().mapResult(lambda) }
}

fun <TValue> Parser<TValue>.peek(action: (TValue) -> Unit): Parser<TValue> {
    return { this@peek().peek(action) }
}