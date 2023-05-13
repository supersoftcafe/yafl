package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflLexer
import com.supersoftcafe.yafl.antlr.YaflParser
import org.antlr.v4.runtime.CharStreams
import org.antlr.v4.runtime.CommonTokenStream

fun sourceToParseTree(rawContents: String, file: String): Pair<String, YaflParser.RootContext> {
    System.err.println("  reading file $file")

    // Add '^' to 'fun' with preceding white space to mark it as a member function
    // for the parser to match. It's a hack to make the parsing logic easier, for now.
    val contents = rawContents.lines().joinToString("\n", "", "\n") {
        val index = it.indexOf("fun")
        if (index > 0 && it.substring(0, index).all { it.isWhitespace() })
            it.substring(0, index-1) + '^' + it.substring(index)
        else it
    }

    val lexer = YaflLexer(CharStreams.fromString(contents))
    val tokenStream = CommonTokenStream(lexer)
    val parser = YaflParser(tokenStream)
    return file to parser.root()
}
