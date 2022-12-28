package com.supersoftcafe.yafl.utils

data class Both<out TValue>(val value: TValue, val error: List<String>) {
    constructor(value: TValue, error: String) : this(value, listOf(error))
    constructor(value: TValue) : this(value, listOf())

    fun <TResult> map(
        op: (TValue) -> Both<TResult>
    ): Both<TResult> {
        val result = op(value)
        return Both(result.value, error + result.error)
    }

    companion object {
        fun <TValue1,TValue2,TResult> merge(
            value1: Both<TValue1>,
            value2: Both<TValue2>,
            op: (TValue1,TValue2) -> Both<TResult>
        ): Both<TResult> {
            val result = op(value1.value, value2.value)
            return Both(result.value, value1.error + value2.error + result.error)
        }

        fun <TValue1,TValue2,TValue3,TResult> merge(
            value1: Both<TValue1>,
            value2: Both<TValue2>,
            value3: Both<TValue3>,
            op: (TValue1,TValue2,TValue3) -> Both<TResult>
        ): Both<TResult> {
            val result = op(value1.value, value2.value, value3.value)
            return Both(result.value, value1.error + value2.error + value3.error + result.error)
        }

        fun <TValue1,TValue2,TValue3,TValue4,TResult> merge(
            value1: Both<TValue1>,
            value2: Both<TValue2>,
            value3: Both<TValue3>,
            value4: Both<TValue4>,
            op: (TValue1,TValue2,TValue3,TValue4) -> Both<TResult>
        ): Both<TResult> {
            val result = op(value1.value, value2.value, value3.value, value4.value)
            return Both(result.value, value1.error + value2.error + value3.error + value4.error + result.error)
        }
    }
}

fun <TValue, TResult> Both<List<TValue>>.mapIndexed(
    op: (Int, TValue) -> Both<TResult>
): Both<List<TResult>> {
    val result = value.mapIndexed(op)
    return Both(result.map { it.value }, result.flatMap { it.error })
}

fun <TValue> Both<TValue>?.asNullable(): Both<TValue?> {
    return if (this == null) {
        Both(null)
    } else {
        Both(value, error)
    }
}

inline  fun <TValue, reified TResult> Both<TValue>.asType(): Both<TResult> {
    return Both(value as TResult, error)
}