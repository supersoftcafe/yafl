package com.supersoftcafe.yaflc

class Tokens private constructor(private val tokens: Array<Token>, private val index: Int) {

    constructor(text: String, file: String) : this(parse(text, file), 0)
    val head get() = tokens[index]
    val tail get() = Tokens(tokens, index + 1)
//    val list get() = tokens.asList().subList(index, tokens.size)


    private companion object {
        fun parse(text: String, file: String): Array<Token> {
            val tokenKinds = TokenKind.values()
            val result = mutableListOf<Token>()
            val blocks = mutableListOf<Int>(0)
            var input = text

            var line = 1
            var character = 1

            while (input.isNotEmpty()) {
//                val groups = regex.find(input)!!.groups
//                val (kind, match) = tokenKinds.firstNotNullOf { groups[it.name]?.let { m -> Pair(it, m.value) } }

                val (kind, match) = tokenKinds.mapNotNull { tokenKind ->
                    val it = tokenKind.rx?.find(input)
                    if (it == null || it.range.first > 0) null
                    else Pair(tokenKind, it.value)
                }.maxByOrNull { it.second.length }!!

                val sourceRef = SourceRef(file, line, character, line, character + match.length - 1)
                input = input.substring(match.length)

                if (kind != TokenKind.IGNORE) {
                    while (character <= blocks.last()) {
                        result += Token(TokenKind.EOB, "", sourceRef)
                        blocks.removeLast()
                    }

                    if (kind.blockStart) {
                        blocks += character
                    }

                    result += Token(kind, match, sourceRef)
                }

                for (chr in match) {
                    if (chr == '\n') {
                        line += 1;
                        character = 1;
                    } else if (chr != '\r') {
                        character += 1;
                    }
                }
            }

            val eofRef = SourceRef(file, line, character, line, character)

            while (1 <= blocks.last()) {
                result += Token(TokenKind.EOB, "", eofRef)
                blocks.removeLast()
            }

            result += Token(TokenKind.EOI, "", eofRef)

            return result.toTypedArray()
        }

//        val regex = Regex(TokenKind.values()
//            .filter { it.pattern.isNotEmpty() }
//            .joinToString("|", "^") { "(?<${it.name}>${it.pattern})" }
//            , RegexOption.MULTILINE)
    }
}