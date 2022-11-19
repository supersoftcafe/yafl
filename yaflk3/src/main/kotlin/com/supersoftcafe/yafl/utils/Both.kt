package com.supersoftcafe.yafl.utils

data class Both<out TValue, TError>(val value: TValue, val error: List<TError>) {
    constructor(value: TValue, error: TError) : this(value, listOf(error))
    constructor(value: TValue) : this(value, listOf())

    fun <TResult> map(
        op: (TValue) -> Both<TResult,TError>
    ): Both<TResult,TError> {
        val result = op(value)
        return Both(result.value, error + result.error)
    }

    companion object {
        fun <TValue1,TValue2,TResult,TError> merge(
            value1: Both<TValue1,TError>,
            value2: Both<TValue2,TError>,
            op: (TValue1,TValue2) -> Both<TResult, TError>
        ): Both<TResult,TError> {
            val result = op(value1.value, value2.value)
            return Both(result.value, value1.error + value2.error + result.error)
        }

        fun <TValue1,TValue2,TValue3,TResult,TError> merge(
            value1: Both<TValue1,TError>,
            value2: Both<TValue2,TError>,
            value3: Both<TValue3,TError>,
            op: (TValue1,TValue2,TValue3) -> Both<TResult, TError>
        ): Both<TResult,TError> {
            val result = op(value1.value, value2.value, value3.value)
            return Both(result.value, value1.error + value2.error + value3.error + result.error)
        }
    }
}

fun <TValue, TResult, TError> Both<List<TValue>, TError>.mapIndexed(
    op: (Int, TValue) -> Both<TResult, TError>
): Both<List<TResult>, TError> {
    val result = value.mapIndexed(op)
    return Both(result.map { it.value }, result.flatMap { it.error })
}

fun <TValue, TError> Both<TValue, TError>?.asNullable(): Both<TValue?, TError> {
    return if (this == null) {
        Both(null)
    } else {
        Both(value, error)
    }
}

inline  fun <TValue, reified TResult, TError> Both<TValue, TError>.asType(): Both<TResult, TError> {
    return Both(value as TResult, error)
}