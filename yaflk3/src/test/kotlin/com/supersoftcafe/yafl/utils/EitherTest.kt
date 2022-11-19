package com.supersoftcafe.yafl.utils

import org.junit.jupiter.api.Test

import org.junit.jupiter.api.Assertions.*

internal class EitherTest {

    @Test
    fun map() {
    }

    @Test
    fun with() {
    }

    @Test
    fun mapIndexed() {

    }

    @Test
    fun flatMapIndexed() {
        val result = Either.some<List<Int>,String>(listOf(1,2,3,4,5,6,7,8))
            .flatMapIndexed { index, value ->
                Either.some(if (value % 2 == 0) listOf(value) else listOf())
            }
        when (result) {
            is Either.Some ->
                assertIterableEquals(listOf(2,4,6,8), result.value)
            else ->
                fail()
        }
    }
}