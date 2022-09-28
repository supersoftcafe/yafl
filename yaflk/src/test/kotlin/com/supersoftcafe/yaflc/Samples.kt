package com.supersoftcafe.yaflc

import com.supersoftcafe.yaflc.asttoir.astToIr
import com.supersoftcafe.yaflc.codegen.generateLlvmIr
import com.supersoftcafe.yaflc.codegen.optimizeLlvmIr
import com.supersoftcafe.yaflc.utils.None
import com.supersoftcafe.yaflc.utils.Some
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.ValueSource

internal class Samples {


    @ParameterizedTest
    @ValueSource(strings = [
        "test0.yafl",
//        "test1.yafl",
//        "test2.yafl",
//        "test3.yafl",
//        "test4.yafl",
//        "test5.yafl",
//        "test6.yafl",
//        "test7.yafl",
//        "test8.yafl",
//        "test9.yafl",
//        "test10.yafl",
//        "test11.yafl",
//        "test12.yafl",
    ])
    fun testBland(file: String) {
        testWithFiles("/bland/$file")
    }


    @ParameterizedTest
    @ValueSource(strings = [
        "unpack.yafl",
        "apply.yafl",
        "interface.yafl",
    ])
    fun testClasses(file: String) {
        testWithFiles("/classes/$file")
    }


    @ParameterizedTest
    @ValueSource(strings = [
        "test1.yafl",
    ])
    fun testSystem(file: String) {
        testWithFiles("/system/system.yafl", "/system/$file")
    }


    fun testWithFiles(vararg files: String) {
        val ast = Ast()

        val parser = GrammarParser(ast)

        for (file in files) {
            val text = Samples::class.java.getResource(file)!!.readText()
            val parseErrors = parser.parseIntoAst(Tokens(text, file))
            assertEquals("", parseErrors.joinToString("\n"))
        }

        val typeResolver = TypeResolver(ast)
        val resolveErrors = typeResolver.resolve()
        assertEquals("", resolveErrors.joinToString("\n"))

        val things = astToIr(ast)
        val llvmIr = generateLlvmIr(things)
        when (llvmIr) {
            is Some<String> -> {
                println(llvmIr)
                val optimised = optimizeLlvmIr(llvmIr.value)
                when (optimised) {
                    is None<String> -> {
                        fail<Unit>("optimizeLlvmIr: " + optimised.error)
                    }

                }
            }
            is None<String> -> {
                fail<Unit>("generateLlvmIr: " + llvmIr.error)
            }
        }
    }
}