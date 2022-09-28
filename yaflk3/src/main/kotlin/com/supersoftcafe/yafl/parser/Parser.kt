package com.supersoftcafe.yafl.parser

import com.supersoftcafe.yafl.lexer.Token
import com.supersoftcafe.yafl.lexer.TokenKind
import com.supersoftcafe.yafl.lexer.Tokens
import com.supersoftcafe.yafl.utils.Tuple2
import com.supersoftcafe.yafl.utils.tupleOf


typealias Parser<TValue> = (Tokens) -> Outcome<Tuple2<TValue, Tokens>>

infix fun <TLeft, TRight> Parser<TLeft>.andThen(right: Parser<TRight>): Parser<Tuple2<TLeft, TRight>> {
    return { tokens ->
        when (val a = invoke(tokens)) {
            is Outcome.Failure -> Outcome.Failure(a.error)
            is Outcome.Success -> when (val b = right.invoke(a.value.v2)) {
                is Outcome.Failure -> Outcome.Failure(b.error)
                is Outcome.Success -> Outcome.Success(tupleOf(tupleOf(a.value.v1, b.value.v1), b.value.v2))
            }
        }
    }
}

infix fun <TLeft, TRight> Parser<TLeft>.discardAndThen(right: Parser<TRight>): Parser<TRight> {
    return this andThen right map { (l,r) -> r }
}

infix fun <TLeft, TRight> Parser<TLeft>.andThenDiscard(right: Parser<TRight>): Parser<TLeft> {
    return this andThen right map { (l,r) -> l }
}

infix fun <TValue> Parser<TValue>.orElse(right: Parser<TValue>): Parser<TValue> {
    return { tokens ->
        when (val a = invoke(tokens)) {
            is Outcome.Success -> a
            is Outcome.Failure -> right(tokens)
        }
    }
}

fun <TValue> optional(right: Parser<TValue>): Parser<TValue?> {
    return { tokens ->
        when (val a = right(tokens)) {
            is Outcome.Failure -> Outcome.Success(tupleOf(null, tokens))
            is Outcome.Success -> Outcome.Success(tupleOf(a.value.v1, a.value.v2))
        }
    }
}

fun <TValue> zeroOrMore(right: Parser<TValue>): Parser<List<TValue>> {
    tailrec fun body(list: List<TValue>, tokens: Tokens): Tuple2<List<TValue>, Tokens> {
        return when (val a = right(tokens)) {
            is Outcome.Failure -> tupleOf(list, tokens)
            is Outcome.Success -> body(list + a.value.v1, a.value.v2)
        }
    }

    return { tokens -> Outcome.Success(body(listOf(), tokens)) }
}

fun <TCond,TValue> repeatWhile(condition: Parser<TCond>, content: Parser<TValue>): Parser<List<TValue>> {
    tailrec fun body(list: List<TValue>, tokens: Tokens): Outcome<Tuple2<List<TValue>, Tokens>> {
        return when (val a = condition(tokens)) {
            is Outcome.Failure -> Outcome.Success(tupleOf(list, tokens))
            is Outcome.Success -> when (val b = content(a.value.v2)) {
                is Outcome.Failure -> Outcome.Failure(b.error)
                is Outcome.Success -> body(list + b.value.v1, b.value.v2)
            }
        }
    }
    return { tokens -> body(listOf(), tokens) }
}

fun <TCond,TValue> repeatUntil(condition: Parser<TCond>, content: Parser<TValue>): Parser<List<TValue>> {
    tailrec fun body(list: List<TValue>, tokens: Tokens): Outcome<Tuple2<List<TValue>, Tokens>> {
        return when (val a = condition(tokens)) {
            is Outcome.Success -> Outcome.Success(tupleOf(list, tokens))
            is Outcome.Failure -> when (val b = content(tokens)) {
                is Outcome.Failure -> Outcome.Failure(b.error)
                is Outcome.Success -> body(list + b.value.v1, b.value.v2)
            }
        }
    }
    return { tokens -> body(listOf(), tokens) }
}

fun <TValue> lazyP(getParser: () -> Parser<TValue>): Parser<TValue> {
    return { tokens ->
        getParser()(tokens)
    }
}

fun match(kind: TokenKind): Parser<Token> {
    return { tokens ->
        if (tokens.head.kind == kind)
             Outcome.Success(tupleOf(tokens.head, tokens.tail))
        else Outcome.Failure("Failed to match $kind")
    }
}

fun matchText(kind: TokenKind): Parser<String> {
    return match(kind) map { it.text }
}

infix fun <TIn, TOut> Parser<TIn>.map(mapper: (TIn)->TOut): Parser<TOut> {
    return { tokens ->
        when (val a = invoke(tokens)) {
            is Outcome.Success -> Outcome.Success(tupleOf(mapper(a.value.v1), a.value.v2))
            is Outcome.Failure -> Outcome.Failure(a.error)
        }
    }
}




data class Module(val name: List<String>)

val function = match(TokenKind.FUN) discardAndThen matchText(TokenKind.NAME)
val fullyQualifiedNameP = matchText(TokenKind.NAME) andThen repeatWhile(matchText(TokenKind.DOT), matchText(TokenKind.NAME)) map { (l,r) -> listOf(l) + r }
val moduleNameP = match(TokenKind.MODULE) discardAndThen fullyQualifiedNameP map { Module(it) }

