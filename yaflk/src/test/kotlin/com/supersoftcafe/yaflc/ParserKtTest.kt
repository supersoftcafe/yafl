package com.supersoftcafe.yaflc

import org.junit.jupiter.api.Test

import org.junit.jupiter.api.Assertions.*

internal class ParserKtTest {

    val tokens = Tokens("module System\n\nuse Blag\n", "file.yafl")

    @Test
    fun oneOf() {
        val result1 = Tokens("module", "").OneOf(TokenKind.MODULE, TokenKind.NAME)
        assertInstanceOf(Result.Ok::class.java, result1)
        assertEquals(TokenKind.MODULE, (result1 as Result.Ok).value.kind)
        assertEquals("module", result1.value.text)

        val result2 = Tokens("System", "").OneOf(TokenKind.MODULE, TokenKind.NAME)
        assertInstanceOf(Result.Ok::class.java, result2)
        assertEquals(TokenKind.NAME, (result2 as Result.Ok).value.kind)
        assertEquals("System", result2.value.text)
    }
}