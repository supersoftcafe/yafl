package com.supersoftcafe.yaflc

import kotlinx.collections.immutable.PersistentList
import kotlinx.collections.immutable.persistentListOf

//class Tokens private constructor(
//    private val input: String,
//    private val file: String,
//    private val line: Int,
//    private val character: Int,
//    private val indent: Int,
//    private val startOfLine: Boolean
//) {
//    constructor(input: String, file: String) : this(input, file, 1, 1, 0, true)
//
//    fun get(vararg lookingFor: TokenKind) = get(this, lookingFor)
//
//    companion object {
//        private tailrec fun get(tk: Tokens, lookingFor: Array<out TokenKind>): Result.Ok<Token> {
//            if (tk.input.isEmpty())
//                return Result.Ok(Token(TokenKind.EOI, "", tk.indent), SourceRef(tk.file, tk.line, tk.character, tk.line, tk.character), tk, 0)
//
//            val found = TokenKind.values().mapNotNull { tokenKind ->
//                tokenKind.rx?.find(tk.input)?.let {
//                    if (it.range.first > 0) null else Pair(tokenKind, it.value)
//                }
//            }.maxByOrNull { it.second.length }
//
//            val (tokenKind, value) = found ?: Pair(TokenKind.UNKNOWN, tk.input.substring(0, 1))
//
//            var newLine = tk.line
//            var newCharacter = tk.character
//            var newIndent = tk.indent
//            var newStartOfLine = tk.startOfLine
//
//            for (chr in value) {
//                if (chr == '\n') {
//                    newLine += 1;
//                    newCharacter = 1;
//                    newStartOfLine = true
//                    newIndent = 0
//                } else {
//                    if (newStartOfLine) {
//                        if (chr == ' ') newIndent += 1;
//                        else newStartOfLine = false;
//                    }
//                    if (chr != '\r')
//                        newCharacter += 1;
//                }
//            }
//
//            val tokens = Tokens(tk.input.substring(value.length), tk.file, newLine, newCharacter, newIndent, newStartOfLine)
//            return if (tokenKind == TokenKind.IGNORE)
//                get(tokens, lookingFor)
//            else
//                Result.Ok(Token(tokenKind,value, tk.indent), SourceRef(tk.file, tk.line, tk.character, newLine, newCharacter), tokens, tk.indent)
//        }
//    }
//}







fun <TValue> Tokens.OneOf(first: Parser<TValue>, vararg others: Parser<TValue>): Result<TValue> {
    return others.fold(first()) { previousResult, second ->
        when (previousResult) {
            is Result.Ok -> previousResult
            is Result.Fail ->
                when (val secondResult = second()) {
                    is Result.Ok -> secondResult
                    is Result.Fail -> previousResult
                    is Result.Absent -> previousResult
                }
            is Result.Absent -> second()
        }
    }
}

fun <V1, V2> Tokens.AllOf(p1: Parser<V1>, p2: Parser<V2>): Result<Tuple2<V1, V2>> =
    when (val result1 = p1()) {
        is Result.Absent -> result1.xfer()
        is Result.Fail -> result1.xfer()
        is Result.Ok -> when (val result2 = result1.tokens.p2()) {
            is Result.Absent -> result2.xfer()
            is Result.Fail -> result2.xfer()
            is Result.Ok -> Result.Ok(tupleOf(result1.value, result2.value), result1.sourceRef + result2.sourceRef, result2.tokens)
        }
    }

fun <V1, V2, V3> Tokens.AllOf(p1: Parser<V1>, p2: Parser<V2>, p3: Parser<V3>) =
    AllOf(p1) { AllOf(p2, p3) }.map { _, (l, r) -> tupleOf(l, r.v1, r.v2) }

fun <V1, V2, V3, V4> Tokens.AllOf(p1: Parser<V1>, p2: Parser<V2>, p3: Parser<V3>, p4: Parser<V4>) =
    AllOf({ AllOf(p1, p2) }, { AllOf(p3, p4) }).map { _, (l, r) -> l + r }

fun <V1, V2, V3, V4, V5> Tokens.AllOf(p1: Parser<V1>, p2: Parser<V2>, p3: Parser<V3>, p4: Parser<V4>, p5: Parser<V5>) =
    AllOf({ AllOf(p1, p2, p3) }, { AllOf(p4, p5) }).map { _, (l, r) -> l + r }

fun <V1, V2, V3, V4, V5, V6> Tokens.AllOf(p1: Parser<V1>, p2: Parser<V2>, p3: Parser<V3>, p4: Parser<V4>, p5: Parser<V5>, p6: Parser<V6>) =
    AllOf({ AllOf(p1, p2, p3) }, { AllOf(p4, p5, p6) }).map { _, (l, r) -> l + r }


fun <TValue> Tokens.Repeat(lambda: Parser<TValue>): Result<PersistentList<TValue>> {
    var loops = 0
    fun Tokens.Repeat(root: PersistentList<TValue>): Result<PersistentList<TValue>> {
        if (++loops == 100) {
            println("break here")
        }
        return when (val result = lambda()) {
            is Result.Ok -> result.tokens.Repeat(root.add(result.value))
            is Result.Fail -> result.xfer()
            is Result.Absent -> Result.Ok(root, result.sourceRef, this)
        }
    }
    return Repeat(persistentListOf())
}

fun <TValue> Tokens.ListOfWhile(separator: Parser<*>, lambda: Parser<TValue>): Result<PersistentList<TValue>> {
    tailrec fun Tokens.ListOfWhile(root: PersistentList<TValue>, sourceRef: SourceRef): Result<PersistentList<TValue>> {
        return when (val sep = separator()) {
            is Result.Absent, is Result.Fail -> Result.Ok(root, sourceRef, this)
            is Result.Ok -> when (val result = lambda(sep.tokens)) {
                is Result.Ok -> result.tokens.ListOfWhile(root.add(result.value), sourceRef + sep.sourceRef + result.sourceRef)
                is Result.Fail -> result.xfer()
                is Result.Absent -> result.xfer()
            }
        }
    }
    return ListOfWhile(persistentListOf(), SourceRef.EMPTY)
}

fun <TValue> Tokens.Parameters(
    open: Parser<*>,
    lambda: Parser<TValue>,
    separator: Parser<*>,
    close: Parser<*>
): Result<PersistentList<TValue>> {
    val result = OneOf(
        { AllOf(open, close).map { _, _ -> persistentListOf() } },
        { AllOf(open, lambda, close).map { _, (_, value, _) -> persistentListOf(value) } },
        { AllOf(open, lambda, { ListOfWhile(separator, lambda) }, close).map { _, (_, value, more, _) -> persistentListOf(value).addAll(more) } }
    )
    return result
}


fun <TValue> Tokens.If(check: Parser<*>, lambda: Parser<TValue>) =
    when (val preamble = check()) {
        is Result.Ok -> lambda(preamble.tokens)
        is Result.Fail -> Result.Ok(null, SourceRef.EMPTY, this)
        is Result.Absent -> Result.Ok(null, SourceRef.EMPTY, this)
    }

fun <TValue> Tokens.FailIsAbsent(lambda: Parser<TValue>) =
    when (val result = lambda()) {
        is Result.Ok -> result
        is Result.Fail -> Result.Absent(result.error.first().first)
        is Result.Absent -> result.xfer()
    }

fun Tokens.TokenIs(vararg kind: TokenKind): Result<Token> {
    val token = head
    return if (token.kind in kind)
        Result.Ok(token, token.sourceRef, tail)
    else
        Result.Fail(token.sourceRef, "Expected token [${kind.joinToString(" / ")}] but got ${token.kind}")
}

fun Tokens.TokenIs(kind: List<TokenKind>): Result<Token> {
    return TokenIs(*kind.toTypedArray())
}
