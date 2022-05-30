package com.supersoftcafe.yaflc

import org.junit.jupiter.api.Test

import org.junit.jupiter.api.Assertions.*
import kotlin.test.assertContains

internal class GrammarParserTest {

    @Test
    fun parseIntoAst() {
        val ast = Ast()
        val parser = GrammarParser(ast)
        val tokens = Tokens("module System\n\nuse Fred\nuse Fred.Bill\n\n\nfun Doit() = 1\n", "test.yafl")
        val errors = parser.parseIntoAst(tokens)

        assertEquals(0, errors.size, errors.joinToString("\n"))
        assertNotNull(ast.modules.firstOrNull { it.name == "System" })
        assertNotNull(ast.modules.firstOrNull { it.name == "Fred" })
        assertNotNull(ast.modules.firstOrNull { it.name == "Fred.Bill" })
    }

    @Test
    fun parseDottyName() {
        val ast1 = Ast()
        val value1 = GrammarParser(ast1).parseDottyName(Tokens("part1", "test.yafl"))

        assertInstanceOf(Result.Ok::class.java, value1)
        assertEquals(listOf("part1"), (value1 as Result.Ok).value)
    }
}