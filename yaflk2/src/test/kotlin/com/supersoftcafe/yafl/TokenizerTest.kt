package com.supersoftcafe.yafl

import com.supersoftcafe.yafl.tokenizer.TokenKind.*
import com.supersoftcafe.yafl.tokenizer.Tokens
import com.supersoftcafe.yafl.tokenizer.Result
import com.supersoftcafe.yafl.tokenizer.TokenKind
import com.supersoftcafe.yafl.tokenizer.tokenize
import org.junit.jupiter.api.Test

import org.junit.jupiter.api.Assertions.*
import kotlin.test.assertContentEquals

internal class TokenizerTest {

    private fun tokens(text: String) = when (val tk = tokenize(text, "file.yafl")) {
        is Result.Some<Tokens> -> tk.value
        else -> throw IllegalStateException()
    }

    @Test
    fun tokenizeModuleHeader() {
        val tk1 = tokens("module System")

        assertEquals(TokenKind.MODULE, tk1.head.kind)

        val tk2 = tk1.tail
        assertEquals(TokenKind.NAME, tk2.head.kind)
        assertEquals("System", tk2.head.text)
    }

    @Test
    fun tokenizeBlockStartAndEnd() {
        val result = tokens(
            "interface\n" +
            "  fun fred() = 3\n" +
            "\n" +
            "val bill = 3\n").list

        val expected = listOf(INTERFACE, FUN, NAME, OBRACKET, CBRACKET, EQ, INTEGER, EOB, VAL, NAME, EQ, INTEGER, EOI)

        assertContentEquals(expected, result.map { it.kind })
    }

}