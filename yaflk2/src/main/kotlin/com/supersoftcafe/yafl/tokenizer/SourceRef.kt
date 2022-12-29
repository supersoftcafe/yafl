package com.supersoftcafe.yafl.tokenizer

data class SourceRef(
    val filename: String,
    val startLine: Int,
    val startCharacter: Int,
    val endLine: Int,
    val endCharacter: Int
) {
    constructor(filename: String, line: Int = 1, character: Int = 1) : this(filename, line, character, line, character)

    operator fun plus(match: String): SourceRef {
        val splits = match.split('\n')
        val count = splits.last().count { it != '\r' }
        return if (splits.size > 1)
            SourceRef(filename, endLine, endCharacter, endLine + splits.size - 1, count)
        else
            SourceRef(filename, endLine, endCharacter, endLine, endCharacter + count)
    }

    operator fun plus(other: SourceRef): SourceRef {
        if (this == EMPTY) {
            return other
        } else if (other == EMPTY) {
            return this
        } else {
            if (filename != other.filename) throw IllegalArgumentException()
            val c1 = startLine > other.startLine || (startLine == other.startLine && startCharacter > other.startCharacter)
            val c2 = endLine < other.endLine || (endLine == other.endLine && endCharacter < other.endCharacter)
            return SourceRef(
                filename,
                if (c1) other.startLine else startLine,
                if (c1) other.startCharacter else startCharacter,
                if (c2) other.endLine else endLine,
                if (c2) other.endCharacter else endCharacter)
        }
    }

    companion object {
        val EMPTY = SourceRef("", 0, 0, 0, 0)
    }
}
