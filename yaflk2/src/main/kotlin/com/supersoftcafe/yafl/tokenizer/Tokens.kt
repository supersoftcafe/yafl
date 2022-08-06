package com.supersoftcafe.yafl.tokenizer

class Tokens constructor(private val tokens: Array<Token>, private val index: Int = 0) {
    val head get() = tokens[index]
    val tail get() = Tokens(tokens, index + 1)
    val list get() = tokens.asList().subList(index, tokens.size)
}