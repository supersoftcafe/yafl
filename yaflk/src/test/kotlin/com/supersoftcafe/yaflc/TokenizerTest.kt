package com.supersoftcafe.yaflc

import org.junit.jupiter.api.Test

import org.junit.jupiter.api.Assertions.*

internal class TokenizerTest {

    private fun tokens(text: String) = Tokens(text, "file.yafl")

    @Test
    fun tokenize() {
        val result1 = tokens("module System").get() as Result.Ok
        assertEquals(TokenKind.MODULE, result1.value.kind)

        val result2 = result1.tokens.get() as Result.Ok
        assertEquals(TokenKind.NAME, result2.value.kind)
        assertEquals("System", result2.value.text)
    }

    @Test
    fun indentOnFirstLine() {
        val t = tokens("   System  Next")

        val result1 = t.get() as Result.Ok
        assertEquals(TokenKind.NAME, result1.value.kind)
        assertEquals(3, result1.value.indent)
        assertEquals(4, result1.sourceRef.startCharacter)
        assertEquals(10, result1.sourceRef.endCharacter)
        assertEquals(1, result1.sourceRef.startLine)
        assertEquals(1, result1.sourceRef.endLine)

        val result2 = result1.tokens.get() as Result.Ok
        assertEquals(TokenKind.NAME, result2.value.kind)
        assertEquals(3, result2.value.indent)
        assertEquals(12, result2.sourceRef.startCharacter)
        assertEquals(16, result2.sourceRef.endCharacter)
        assertEquals(1, result2.sourceRef.startLine)
        assertEquals(1, result2.sourceRef.endLine)
    }

    @Test
    fun indentOnSecondLine() {
        val t = tokens("\n   System  Next")

        val result1 = t.get() as Result.Ok
        assertEquals(TokenKind.NAME, result1.value.kind)
        assertEquals(3, result1.value.indent)
        assertEquals(4, result1.sourceRef.startCharacter)
        assertEquals(10, result1.sourceRef.endCharacter)
        assertEquals(2, result1.sourceRef.startLine)
        assertEquals(2, result1.sourceRef.endLine)

        val result2 = result1.tokens.get() as Result.Ok
        assertEquals(TokenKind.NAME, result2.value.kind)
        assertEquals(3, result2.value.indent)
        assertEquals(12, result2.sourceRef.startCharacter)
        assertEquals(16, result2.sourceRef.endCharacter)
        assertEquals(2, result2.sourceRef.startLine)
        assertEquals(2, result2.sourceRef.endLine)
    }
}