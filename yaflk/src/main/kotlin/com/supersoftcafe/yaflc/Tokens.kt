package com.supersoftcafe.yaflc

class Tokens private constructor(private val tokens: Array<Token>, private val index: Int) {

    constructor(text: String, file: String) : this(parse(text, file), 0)
    val head get() = tokens[0]
    val tail get() = Tokens(tokens, index + 1)
    val list get() = tokens.asList().subList(index, tokens.size)


    private companion object {
        fun parse(text: String, file: String): Array<Token> {
            val tokenKinds = TokenKind.values()
            val result = mutableListOf<Token>()
            val blocks = mutableListOf<Int>()
            var input = text

            var line = 0
            var indent = 0
            var character = 0
            var startOfLine = true

            while (input.isNotEmpty()) {
                val groups = regex.find(input)!!.groups
                val (kind, match) = tokenKinds.firstNotNullOf { groups[it.name]?.let { m -> Pair(it, m.value) } }
                val sourceRef = SourceRef(file, line, character, line, character + match.length - 1)
                input = input.substring(match.length)

                if (blocks.isNotEmpty() && indent <= blocks.last()) {
                    result += Token(TokenKind.EOB, "", SourceRef.EMPTY)
                    blocks.removeLast()
                }

                if (kind.blockStart) {
                    blocks += indent
                }

                if (kind != TokenKind.IGNORE) {
                    result += Token(kind, match, sourceRef)
                }

                for (chr in match) {
                    if (chr == '\n') {
                        line += 1;
                        character = 1;
                        startOfLine = true
                        indent = 0
                    } else {
                        if (startOfLine) {
                            if (chr == ' ') indent += 1;
                            else startOfLine = false;
                        }
                        if (chr != '\r')
                            character += 1;
                    }
                }
            }

            while (blocks.isNotEmpty()) {
                result += Token(TokenKind.EOB, "", SourceRef.EMPTY)
                blocks.removeLast()
            }

            result += Token(TokenKind.EOI, "", SourceRef.EMPTY)

            return result.toTypedArray()
        }

        val regex = Regex(TokenKind.values()
            .filter { it.pattern.isNotEmpty() }
            .joinToString("|", "^") { "(?<${it.name}>${it.pattern})" }
            , RegexOption.MULTILINE)
    }
}