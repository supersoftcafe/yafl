package com.supersoftcafe.yaflc.utils

sealed class Either<TValue> {
    abstract fun <TResult> map(op: (TValue) -> Either<TResult>): Either<TResult>
}

data class Some<TValue>(val value: TValue) : Either<TValue>() {
    override fun <TResult> map(op: (TValue) -> Either<TResult>): Either<TResult> {
        return op(value)
    }
}

data class None<TValue>(val error: List<String>) : Either<TValue>() {
    constructor(error: String) : this(listOf(error))

    override fun <TResult> map(op: (TValue) -> Either<TResult>): Either<TResult> {
        return None<TResult>(error)
    }
}
