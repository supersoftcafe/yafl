package com.supersoftcafe.yaflc

import org.junit.jupiter.api.Test

import org.junit.jupiter.api.Assertions.*

internal class TokenizerTest {

    private fun tokens(text: String) = Tokens(text, "file.yafl")

    @Test
    fun tokenize() {
        val tk1 = tokens("module System")
        assertEquals(TokenKind.MODULE, tk1.head.kind)

        val tk2 = tk1.tail
        assertEquals(TokenKind.NAME, tk2.head.kind)
        assertEquals("System", tk2.head.text)
    }

}