package com.supersoftcafe.yafl

import com.supersoftcafe.yafl.utils.Some
import com.supersoftcafe.yafl.utils.TextSource
import org.junit.jupiter.api.Test
import org.opentest4j.AssertionFailedError
import yaflBuild
import com.supersoftcafe.yafl.utils.*

class BasicTest {

    @Test
    fun `return simple literal`() {
        compile(
            "module Test",
            "fun main() => 1")
    }

    fun compile(vararg content: String): String {
        return when (val result = yaflBuild(listOf(TextSource.fromString("test.yafl", content.joinToString(separator = "\n"))))) {
            is Some -> result.value
            is None -> throw AssertionFailedError(result.error.joinToString())
        }
    }
}