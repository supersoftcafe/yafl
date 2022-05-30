package com.supersoftcafe.yaflc

data class SourceRef(
    val file: String,
    val startLine: Int,
    val startCharacter: Int,
    val endLine: Int,
    val endCharacter: Int
) {
    operator fun plus(other: SourceRef): SourceRef {
        if (this == EMPTY) {
            return other
        } else if (other == EMPTY) {
            return this
        } else {
            if (file != other.file) throw IllegalArgumentException()
            val c1 = startLine > other.startLine || (startLine == other.startLine && startCharacter > other.startCharacter)
            val c2 = endLine < other.endLine || (endLine == other.endLine && endCharacter < other.endCharacter)
            return SourceRef(
                file,
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