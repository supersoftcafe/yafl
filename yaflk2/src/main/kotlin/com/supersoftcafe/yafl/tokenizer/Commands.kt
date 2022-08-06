package com.supersoftcafe.yafl.tokenizer

fun tokenize(text: String, filename: String): Result<Tokens> {
    val tokenKinds = TokenKind.values()
    val result = mutableListOf<Token>()
    val blocks = mutableListOf<Int>(0)
    var input = text

    var sourceRef = SourceRef(filename)

    while (input.isNotEmpty()) {
        val (kind, match) = tokenKinds.mapNotNull { tokenKind ->
            val it = tokenKind.rx?.find(input)
            if (it != null && it.range.first == 0)
                Pair(tokenKind, it.value)
            else null
        }.maxByOrNull { it.second.length }
            ?: return Result.None(listOf(Pair(sourceRef, "Unexpected character")))

        sourceRef += match
        input = input.substring(match.length)

        if (kind != TokenKind.IGNORE) {
            while (sourceRef.startCharacter <= blocks.last()) {
                result += Token(TokenKind.EOB, "", sourceRef)
                blocks.removeLast()
            }

            if (kind.blockStart) {
                blocks += sourceRef.startCharacter
            }

            result += Token(kind, match, sourceRef)
        }
    }

    while (1 <= blocks.last()) {
        result += Token(TokenKind.EOB, "", sourceRef)
        blocks.removeLast()
    }

    result += Token(TokenKind.EOI, "", sourceRef)
    return Result.Some(Tokens(result.toTypedArray()))
}

