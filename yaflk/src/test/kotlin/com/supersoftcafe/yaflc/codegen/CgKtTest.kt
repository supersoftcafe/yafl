package com.supersoftcafe.yaflc.codegen

import com.supersoftcafe.yaflc.utils.*
import org.junit.jupiter.api.Test

import org.junit.jupiter.api.Assertions.*
import kotlin.random.Random

internal class CgKtTest {


    @Test
    fun `a simple function`() {
        val main = CgThingFunction.main(CgOp.Label("start"), CgOp.Return(CgTypePrimitive.INT32, "0"))
        val text = Some(listOf(main))
            .map(::generateLlvmIr)
            .map(::optimizeLlvmIr)
        assertInstanceOf(Some::class.java, text)
    }

    @Test
    fun `a simple class`() {
        val main = CgThingFunction.main(CgOp.Label("start"), CgOp.Return(CgTypePrimitive.INT32, "0"))
        val func = CgThingFunction(
            "add",
            CgTypePrimitive.INT32,
            CgThingVariable.THIS,
            CgThingVariable("%number", CgTypePrimitive.INT32),
            CgOp.Label("start"),
            CgOp.Binary("%result", CgTypePrimitive.INT32, CgBinaryOp.ADD, "%number", "27"),
            CgOp.Return(CgTypePrimitive.INT32, "%result")
        )
        val delete = CgThingFunction.nothing("Nums\$delete")
        val klass = CgThingClass("Nums", listOf(), listOf(func), delete)

        val text = Some(listOf(main, func, delete, klass))
            .map(::generateLlvmIr)
            .map(::optimizeLlvmIr)
        assertInstanceOf(Some::class.java, text)

    }

    @Test
    fun `vtable collisions`() {
        val range = (0..9)

        val someFunctions = range.map { CgThingFunction.nothing("make$it") }
        val delete = CgThingFunction.nothing("Numbers\$del")
        val oneClass = CgThingClass("Numbers", emptyList(), someFunctions, delete)

        val body = listOf(CgOp.Label("start")) +
                CgOp.New("%kl", "Numbers") +
                range.flatMap {
                    listOf(
                        CgOp.LoadVirtualCallable("%method$it", "%kl", "make$it"),
                        CgOp.Call("%temp$it", CgTypePrimitive.VOID, "%method$it", listOf())
                    )
                } +
                listOf(CgOp.Return(CgTypePrimitive.INT32, "0"))

        val main = CgThingFunction.main(*body.toTypedArray())

        val text = Some(someFunctions + listOf(delete, main) + oneClass)
            .map(::generateLlvmIr)
            .map(::optimizeLlvmIr)
        assertInstanceOf(Some::class.java, text)
    }
}
