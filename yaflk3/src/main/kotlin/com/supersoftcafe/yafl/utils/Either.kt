package com.supersoftcafe.yafl.utils

import java.io.File

sealed class Either<out TValue> {
    abstract fun <TResult> map(op: (TValue) -> Either<TResult>): Either<TResult>
    abstract fun <TExtra> with(extra: TExtra): Either<Pair<TValue, TExtra>>
}

fun <TValue> some(value: TValue) : Either<TValue> = Some(value)
data class Some<TValue>(val value: TValue) : Either<TValue>() {
    override fun <TResult> map(op: (TValue) -> Either<TResult>) = op(value)
    override fun <TExtra> with(extra: TExtra) = some(Pair(value, extra))
}

fun <TValue> none(errorInfo: Iterable<ErrorInfo>) : Either<TValue> = None(errorInfo)
fun <TValue> none(errorInfo: ErrorInfo) : Either<TValue> = none(listOf(errorInfo))
fun <TValue> none(errorInfo: String) : Either<TValue> = none(ErrorInfo.StringErrorInfo(errorInfo))
data class None<TValue>(val error: Iterable<ErrorInfo>) : Either<TValue>() {
    override fun <TResult> map(op: (TValue) -> Either<TResult>) = None<TResult>(error)
    override fun <TExtra> with(extra: TExtra) = none<Pair<TValue,TExtra>>(error)
}

fun <TResult, TVal1, TVal2> combine(
    val1: Either<TVal1>, val2: Either<TVal2>,
    op: (TVal1, TVal2) -> Either<TResult>
): Either<TResult> {
    return when (val1) {
        is None -> None(val1.error)
        is Some -> when (val2) {
            is None -> None(val2.error)
            is Some -> op(val1.value, val2.value)
        }
    }
}

fun <TResult, TVal1, TVal2, TVal3> combine(
    val1: Either<TVal1>, val2: Either<TVal2>, val3: Either<TVal3>,
    op: (TVal1, TVal2, TVal3) -> Either<TResult>
): Either<TResult> {
    return when (val1) {
        is None -> None(val1.error)
        is Some -> when (val2) {
            is None -> None(val2.error)
            is Some -> when (val3) {
                is None -> None(val3.error)
                is Some ->  op(val1.value, val2.value, val3.value)
            }
        }
    }
}

fun <TResult, TVal1, TVal2, TVal3, TVal4> combine(
    val1: Either<TVal1>, val2: Either<TVal2>,
    val3: Either<TVal3>, val4: Either<TVal4>,
    op: (TVal1, TVal2, TVal3, TVal4) -> Either<TResult>
): Either<TResult> {
    return when (val1) {
        is None -> None(val1.error)
        is Some -> when (val2) {
            is None -> None(val2.error)
            is Some -> when (val3) {
                is None -> None(val3.error)
                is Some -> when (val4) {
                    is None -> None(val4.error)
                    is Some -> op(val1.value, val2.value, val3.value, val4.value)
                }
            }
        }
    }
}


fun <TValue, TResult> Either<List<TValue>>.foldIndexed(
    initial: TResult,
    op: (Int, TResult, TValue) -> Either<TResult>
): Either<TResult> {
    return when (this) {
        is None -> none(error)
        is Some -> value.foldIndexed(some(initial)) { index, acc, value ->
            when (acc) {
                is None -> none(acc.error)
                is Some -> op(index, acc.value, value)
            }
        }
    }
}

fun <TValue, TResult> Either<List<TValue>>.mapList(
    op: (TValue) -> Either<TResult>
): Either<List<TResult>> {
    when (this) {
        is None -> return none(error)
        is Some -> {
            val result = mutableListOf<TResult>()
            for (item in value) {
                when (val r = op(item)) {
                    is None -> return none(r.error)
                    is Some -> result.add(r.value)
                }
            }
            return some(result)
        }
    }
}

private fun <TValue, TResult, TResultContainer> Either<List<TValue>>.mapIndexed(
    mix: (List<TResult>, TResultContainer) -> List<TResult>,
    op: (Int, TValue) -> Either<TResultContainer>
): Either<List<TResult>> {
    return foldIndexed(listOf()) { index, acc, value ->
        when (val result = op(index, value)) {
            is None -> none(result.error)
            is Some -> some(mix(acc, result.value))
        }
    }
}

fun <TValue, TResult> Either<List<TValue>>.mapIndexed(
    op: (Int, TValue) -> Either<TResult>
): Either<List<TResult>> {
    return mapIndexed({ list, result -> list + result }, op)
}

fun <TValue, TResult> Either<List<TValue>>.mapIndexedNotNull(
    op: (Int, TValue) -> Either<TResult?>
): Either<List<TResult>> {
    return mapIndexed({ list, result -> if (result != null) list + result else list }, op)
}

fun <TValue, TResult> Either<List<TValue>>.flatMapIndexed(
    op: (Int, TValue) -> Either<List<TResult>>
): Either<List<TResult>> {
    return mapIndexed({ list, result -> list + result }, op)
}





fun <TValue, TResult> Iterable<Either<TValue>>.foldEither(
    initial: Either<TResult>,
    op: (TResult, TValue) -> Either<TResult>
): Either<TResult> {
    return fold<Either<TValue>, Either<TResult>>(initial) { previous, value ->
        when (previous) {
            is None -> None(previous.error)
            is Some -> when (value) {
                is None -> None(value.error)
                is Some -> op(previous.value, value.value)
            }
        }
    }
}

fun <TValue, TResult> Iterable<Either<TValue>>.foldIndexedEither(
    initial: Either<TResult>,
    op: (Int, TResult, TValue) -> Either<TResult>
): Either<TResult> {
    return foldIndexed<Either<TValue>, Either<TResult>>(initial) { index, previous, value ->
        when (previous) {
            is None -> None(previous.error)
            is Some -> when (value) {
                is None -> None(value.error)
                is Some -> op(index, previous.value, value.value)
            }
        }
    }
}


fun <TValue> Iterable<Either<TValue>>.allOrNothing(): Either<List<TValue>> {
    val result = mapNotNull { (it as? Some)?.value }
    return if (result.size != count())
        none(flatMap { (it as? None)?.error ?: listOf() })
    else some(result)
}


fun readFile(file: File): Either<String> {
    return try {
        some(file.readText())
    } catch (e: Exception) {
        none(ErrorInfo.ParseExceptionInfo(file, e))
    }
}