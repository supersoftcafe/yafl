package com.supersoftcafe.yafl.models.ast

import org.antlr.v4.runtime.ParserRuleContext

data class SourceRef(
    val file: String,
    val startLine: Int,
    val startOffset: Int,
    val stopLine: Int,
    val stopOffset: Int
) {
    constructor(file: String, context: ParserRuleContext) : this(
        file,
        context.start.line,
        context.start.charPositionInLine,
        context.stop.line,
        context.stop.charPositionInLine
    )

    override fun toString() = "$file($startLine:$startOffset,$stopLine:$stopOffset)"

    companion object {
        val EMPTY = SourceRef("", 0, 0, 0, 0)
    }
}
