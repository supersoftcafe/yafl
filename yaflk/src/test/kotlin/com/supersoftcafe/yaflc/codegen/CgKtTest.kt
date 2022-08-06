package com.supersoftcafe.yaflc.codegen

import com.supersoftcafe.yaflc.utils.*
import org.junit.jupiter.api.Test

import org.junit.jupiter.api.Assertions.*
import kotlin.random.Random

internal class CgKtTest {



    @Test
    fun `a simple function`() {
        val main = CgThingFunction.main(CgCodeBlock("start", CgOp.Return(CgTypePrimitive.INT32, "0")))
        val text = Some(listOf(main))
            .map(::generateLlvmIr)
            .map(::optimizeLlvmIr)
        assertInstanceOf(Some::class.java, text)
    }

    @Test
    fun `a simple class`() {
        val main = CgThingFunction.main(CgCodeBlock("start", CgOp.Return(CgTypePrimitive.INT32, "0")))
        val func = CgThingFunction("add", CgTypePrimitive.INT32, CgThingVariable.THIS, CgThingVariable("%number", CgTypePrimitive.INT32), CgCodeBlock("start", CgOp.Binary("%result", CgTypePrimitive.INT32, CgBinaryOp.ADD, "%number", "27"), CgOp.Return(CgTypePrimitive.INT32, "%result")))
        val delete = CgThingFunction.nothing("Nums\$delete")
        val klass = CgThingClass("Nums", listOf(), listOf(func), delete)

        val text = Some(listOf(main, func, delete, klass))
            .map(::generateLlvmIr)
            .map(::optimizeLlvmIr)
        assertInstanceOf(Some::class.java, text)

    }

    @Test
    fun `class with a few methods`() {
        val someFunctions = (0..9).map { CgThingFunction.nothing("make$it") }
        val delete = CgThingFunction.nothing("Numbers\$del")
        val oneClass = CgThingClass("Numbers", emptyList(), someFunctions, delete)
        val main = CgThingFunction.main(
            CgCodeBlock("start",
                listOf(CgOp.New("%kl", "Numbers")) +
                (0..9).flatMap { listOf(
                    CgOp.LoadVirtualCallable("%method$it", "%kl", "make$it"),
                    CgOp.Call("%temp$it", CgTypePrimitive.VOID, "%method$it", listOf())
                ) } +
                listOf(CgOp.Return(CgTypePrimitive.INT32, "0"))
            )
        )

        val text = Some(someFunctions + listOf(delete, main) + oneClass)
            .map(::generateLlvmIr)
            .map(::optimizeLlvmIr)
        assertInstanceOf(Some::class.java, text)
    }

    @Test
    fun `vtable collisions`() {


        val someFunctions = (0..9).map { CgThingFunction.nothing("make$it") }
        val delete = CgThingFunction.nothing("Numbers\$del")
        val oneClass = CgThingClass("Numbers", emptyList(), someFunctions, delete)
        val main = CgThingFunction.main(
            CgCodeBlock("start",
                listOf(CgOp.New("%kl", "Numbers")) +
                        (0..9).flatMap { listOf(
                            CgOp.LoadVirtualCallable("%method$it", "%kl", "make$it"),
                            CgOp.Call("%temp$it", CgTypePrimitive.VOID, "%method$it", listOf())
                        ) } +
                        listOf(CgOp.Return(CgTypePrimitive.INT32, "0"))
            )
        )

        val text = Some(someFunctions + listOf(delete, main) + oneClass)
            .map(::generateLlvmIr)
            .map(::optimizeLlvmIr)
        assertInstanceOf(Some::class.java, text)
    }

    fun createClass(name: String): List<CgThing> {
        val someFunctions = (0..9).map { CgThingFunction.nothing(createRandomizedName(name.hashCode() + it)) }
        val delete = CgThingFunction.nothing("Numbers\$del")
        val oneClass = CgThingClass("Numbers", emptyList(), someFunctions, delete)
        val main = CgThingFunction.main(
            CgCodeBlock("start",
                listOf(CgOp.New("%kl", "Numbers")) +
                        (0..9).flatMap { listOf(
                            CgOp.LoadVirtualCallable("%method$it", "%kl", "make$it"),
                            CgOp.Call("%temp$it", CgTypePrimitive.VOID, "%method$it", listOf())
                        ) } +
                        listOf(CgOp.Return(CgTypePrimitive.INT32, "0"))
            )
        )
    }

    fun createRandomizedName(seed: Int): String {
        val rand = Random(seed).nextInt(0, Int.MAX_VALUE)
        return "func$rand"
    }
}
