package com.supersoftcafe.yaflc

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.ValueSource

internal class Samples {


    @ParameterizedTest
    @ValueSource(strings = [
//        "test1.yafl",
//        "test2.yafl",
//        "test3.yafl",
        "test4.yafl",
    ])
    fun loadAndTest(file: String) {
        val text = Samples::class.java.getResource("/$file")!!.readText()
        val ast = Ast()

        val parser = GrammarParser(ast)
        val tokens = Tokens(text, file)
        val parseErrors = parser.parseIntoAst(tokens)
        assertEquals("", parseErrors.joinToString("\n"))

        val typeResolver = TypeResolver(ast)
        val resolveErrors = typeResolver.resolve()
        assertEquals("", resolveErrors.joinToString("\n"))

        val generator = CodeGenerator(ast)
        val code = generator.generate()
        println(code)
    }
}