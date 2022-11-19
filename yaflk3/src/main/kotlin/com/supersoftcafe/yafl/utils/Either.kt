package com.supersoftcafe.yafl.utils

sealed class Either<TValue,TError> {
    abstract fun <TResult> map(op: (TValue) -> Either<TResult,TError>): Either<TResult,TError>

    abstract fun <TExtra> with(extra: TExtra): Either<Pair<TValue, TExtra>, TError>

    data class Some<TValue,TError>(val value: TValue) : Either<TValue,TError>() {
        override fun <TResult> map(op: (TValue) -> Either<TResult,TError>) = op(value)
        override fun <TExtra> with(extra: TExtra) = some<Pair<TValue,TExtra>,TError>(Pair(value, extra))
    }

    data class Error<TValue,TError>(val error: TError) : Either<TValue,TError>() {
        override fun <TResult> map(op: (TValue) -> Either<TResult,TError>) = Error<TResult,TError>(error)
        override fun <TExtra> with(extra: TExtra) = error<Pair<TValue,TExtra>,TError>(error)
    }

    companion object {
        fun <TValue,TError> some(value: TValue) : Either<TValue,TError> = Some(value)
        fun <TValue,TError> error(error: TError) : Either<TValue,TError> = Error(error)

        fun <TResult, TVal1, TVal2, TError> combine(
            val1: Either<TVal1, TError>,
            val2: Either<TVal2, TError>,
            op: (TVal1, TVal2) -> Either<TResult, TError>
        ): Either<TResult, TError> {
            return when (val1) {
                is Error -> Error(val1.error)
                is Some -> when (val2) {
                    is Error -> Error(val2.error)
                    is Some -> op(val1.value, val2.value)
                }
            }
        }

        fun <TResult, TVal1, TVal2, TVal3, TError> combine(
            val1: Either<TVal1, TError>,
            val2: Either<TVal2, TError>,
            val3: Either<TVal3, TError>,
            op: (TVal1, TVal2, TVal3) -> Either<TResult, TError>
        ): Either<TResult, TError> {
            return when (val1) {
                is Error -> Error(val1.error)
                is Some -> when (val2) {
                    is Error -> Error(val2.error)
                    is Some -> when (val3) {
                        is Error -> Error(val3.error)
                        is Some ->  op(val1.value, val2.value, val3.value)
                    }
                }
            }
        }

        fun <TResult, TVal1, TVal2, TVal3, TVal4, TError> combine(
            val1: Either<TVal1, TError>,
            val2: Either<TVal2, TError>,
            val3: Either<TVal3, TError>,
            val4: Either<TVal4, TError>,
            op: (TVal1, TVal2, TVal3, TVal4) -> Either<TResult, TError>
        ): Either<TResult, TError> {
            return when (val1) {
                is Error -> Error(val1.error)
                is Some -> when (val2) {
                    is Error -> Error(val2.error)
                    is Some -> when (val3) {
                        is Error -> Error(val3.error)
                        is Some -> when (val4) {
                            is Error -> Error(val4.error)
                            is Some -> op(val1.value, val2.value, val3.value, val4.value)
                        }
                    }
                }
            }
        }
    }
}


fun <TValue, TResult, TError> Either<List<TValue>, TError>.foldIndexed(
    initial: TResult,
    op: (Int, TResult, TValue) -> Either<TResult, TError>
): Either<TResult, TError> {
    return when (this) {
        is Either.Error -> Either.error(error)
        is Either.Some -> value.foldIndexed(Either.some(initial)) { index, acc, value ->
            when (acc) {
                is Either.Error -> Either.error(acc.error)
                is Either.Some -> op(index, acc.value, value)
            }
        }
    }
}

private fun <TValue, TResult, TResultContainer, TError> Either<List<TValue>, TError>.mapIndexed(
    mix: (List<TResult>, TResultContainer) -> List<TResult>,
    op: (Int, TValue) -> Either<TResultContainer, TError>
): Either<List<TResult>, TError> {
    return foldIndexed(listOf()) { index, acc, value ->
        when (val result = op(index, value)) {
            is Either.Error -> Either.error(result.error)
            is Either.Some -> Either.some(mix(acc, result.value))
        }
    }
}

fun <TValue, TResult, TError> Either<List<TValue>, TError>.mapIndexed(
    op: (Int, TValue) -> Either<TResult, TError>
): Either<List<TResult>, TError> {
    return mapIndexed({ list, result -> list + result }, op)
}

fun <TValue, TResult, TError> Either<List<TValue>, TError>.mapIndexedNotNull(
    op: (Int, TValue) -> Either<TResult?, TError>
): Either<List<TResult>, TError> {
    return mapIndexed({ list, result -> if (result != null) list + result else list }, op)
}

fun <TValue, TResult, TError> Either<List<TValue>, TError>.flatMapIndexed(
    op: (Int, TValue) -> Either<List<TResult>, TError>
): Either<List<TResult>, TError> {
    return mapIndexed({ list, result -> list + result }, op)
}





fun <TValue, TResult, TError> Iterable<Either<TValue, TError>>.foldEither(
    initial: Either<TResult,TError>,
    op: (TResult, TValue) -> Either<TResult, TError>
): Either<TResult, TError> {
    return fold<Either<TValue, TError>, Either<TResult, TError>>(initial) { previous, value ->
        when (previous) {
            is Either.Error -> Either.Error(previous.error)
            is Either.Some -> when (value) {
                is Either.Error -> Either.Error(value.error)
                is Either.Some -> op(previous.value, value.value)
            }
        }
    }
}

fun <TValue, TResult, TError> Iterable<Either<TValue, TError>>.foldIndexedEither(
    initial: Either<TResult,TError>,
    op: (Int, TResult, TValue) -> Either<TResult, TError>
): Either<TResult, TError> {
    return foldIndexed<Either<TValue, TError>, Either<TResult, TError>>(initial) { index, previous, value ->
        when (previous) {
            is Either.Error -> Either.Error(previous.error)
            is Either.Some -> when (value) {
                is Either.Error -> Either.Error(value.error)
                is Either.Some -> op(index, previous.value, value.value)
            }
        }
    }
}
