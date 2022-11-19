package com.supersoftcafe.yafl.ast

import org.junit.jupiter.api.Test

import org.junit.jupiter.api.Assertions.*

internal class TypeHintsTest {

    @Test
    fun plus() {
        val a = typeHintsOf(6L to TypeHint(SourceRef("a", 1, 2, 3, 4), TypeRef.Primitive(PrimitiveKind.Int32)))
        val b = typeHintsOf(7L to TypeHint(SourceRef("a", 1, 2, 3, 4), TypeRef.Primitive(PrimitiveKind.Int32)))
        val c = typeHintsOf(7L to TypeHint(SourceRef("a", 1, 2, 3, 4), TypeRef.Primitive(PrimitiveKind.Int64)))
        val x = a + b + c
        assertEquals(2, x.lookup.size)
        assertEquals(1, x[6L].size)
        assertEquals(2, x[7L].size)
    }
}