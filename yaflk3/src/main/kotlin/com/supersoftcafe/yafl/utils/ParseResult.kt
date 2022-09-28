package com.supersoftcafe.yafl.utils


sealed class ParseResult<out TValue, out TInput> {

    data class Matched<TValue, TInput>(val input: TInput, val value: TValue, val sourceRef: SourceRef) : ParseResult<TValue, TInput>()

    data class Absent<TValue, TInput>(val input: TInput) : ParseResult<TValue, TInput>()

    data class Error<TValue, TInput>(val input: TInput, val error: List<Tuple2<SourceRef, String>>) : ParseResult<TValue, TInput>() {
        constructor(input: TInput, sourceRef: SourceRef, message: String) : this(input, listOf(tupleOf(sourceRef, message)))
    }

    fun <TOut> map(lambda: (SourceRef, TValue) -> TOut): ParseResult<TOut, TInput> {
        return when (this) {
            is Matched -> Matched(input, lambda(sourceRef, value), sourceRef)
            is Error -> Error(input, error)
            is Absent -> Absent(input)
        }
    }
}