package com.supersoftcafe.yafl.tokenizer

sealed class Result<TValue>() {
    abstract fun plus(func: (TValue) -> Result<TValue>): Result<TValue>

    class Some<TValue>(val value: TValue) : Result<TValue>() {
        override fun plus(func: (TValue) -> Result<TValue>): Result<TValue> {
            return func(value)
        }
    }

    class None<TValue>(val error: List<Pair<SourceRef, String>>) : Result<TValue>() {
        override fun plus(func: (TValue) -> Result<TValue>): Result<TValue> {
            return this
        }
    }
}
