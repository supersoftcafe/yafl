package com.supersoftcafe.yafl.passes.p1_parse

import com.supersoftcafe.yafl.antlr.YaflLexer
import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.ErrorInfo
import com.supersoftcafe.yafl.utils.some
import org.antlr.v4.runtime.*
import org.antlr.v4.runtime.atn.ATNConfigSet
import org.antlr.v4.runtime.dfa.DFA
import java.io.File
import java.util.*

fun sourceToParseTree(file: File, contents: String): Either<YaflParser.RootContext> {
    return try {
        val lexer = YaflLexer(CharStreams.fromString(contents))
        val tokenStream = CommonTokenStream(lexer)
        val parser = YaflParser(tokenStream)

        val errors = mutableListOf<ErrorInfo>()
        parser.addErrorListener(object: ANTLRErrorListener {
            override fun syntaxError(recognizer: Recognizer<*, *>?, offendingSymbol: Any?,
                line: Int, charPositionInLine: Int, msg: String?, e: RecognitionException?) {
                errors.add(ErrorInfo.FileOffsetInfo(file, line, charPositionInLine, msg))
            }

            override fun reportAmbiguity(recognizer: Parser?, dfa: DFA?,
                startIndex: Int, stopIndex: Int, exact: Boolean, ambigAlts: BitSet?, configs: ATNConfigSet?) {}

            override fun reportAttemptingFullContext(recognizer: Parser?, dfa: DFA?,
                startIndex: Int, stopIndex: Int, conflictingAlts: BitSet?, configs: ATNConfigSet?) {}

            override fun reportContextSensitivity(recognizer: Parser?, dfa: DFA?,
                startIndex: Int, stopIndex: Int, prediction: Int, configs: ATNConfigSet?) {}
        })

        val result = parser.root()
        if (errors.isNotEmpty()) {
            error(errors)
        } else {
            some(result)
        }

    } catch (e: Exception) {
        error(ErrorInfo.ParseExceptionInfo(file, e))
    }
}
