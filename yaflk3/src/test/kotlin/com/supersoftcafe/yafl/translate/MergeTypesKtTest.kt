package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.models.ast.Ast
import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.TypeRef
import com.supersoftcafe.yafl.passes.p1_parse.parseToAst
import com.supersoftcafe.yafl.passes.p1_parse.sourceToParseTree
import com.supersoftcafe.yafl.passes.p2_resolve.resolveTypes
import com.supersoftcafe.yafl.passes.p3_infer.inferTypes
import com.supersoftcafe.yafl.passes.p4_optimise.genericSpecialization
import com.supersoftcafe.yafl.passes.p4_optimise.lambdaToClass
import com.supersoftcafe.yafl.passes.p4_optimise.stringsToGlobals
import com.supersoftcafe.yafl.passes.p5_generate.convertToIntermediate
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.Namer
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

internal class MergeTypesKtTest {

    @Test
    fun `given an immediate constant, let is of type int`() {
        val ast = yaflBuild(
                "let value = 1\n"+
                "fun main(): Int32 => 1\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::value" }?.declaration as? Declaration.Value
        assertEquals(TypeRef.Int32, decl?.typeRef)
    }

    @Test
    fun `given an immediate constant, function is of type int`() {
        val ast = yaflBuild(
                "fun main() => 1")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `function is used with int, so parameter type becomes int`() {
        val ast = yaflBuild(
                "fun value87(a) => a\n" +
                "fun main() => value87(87)\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::value87" }?.declaration as? Declaration.Function
        val param_a = decl?.parameters?.firstOrNull { it.name == "a" }
        assertEquals(TypeRef.Int32, decl?.returnType)
        assertEquals(TypeRef.Int32, param_a?.typeRef)
    }

    @Test
    fun `function is used with int + int, so parameter type becomes int`() {
        val ast = yaflBuild(
                "fun value(a, b) => a + b\n" +
                "fun main() => value(1, 2)\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::value" }?.declaration as? Declaration.Function
        val param_a = decl?.parameters?.firstOrNull { it.name == "a" }
        val param_b = decl?.parameters?.firstOrNull { it.name == "b" }
        assertEquals(TypeRef.Int32, decl?.returnType)
        assertEquals(TypeRef.Int32, param_a?.typeRef)
        assertEquals(TypeRef.Int32, param_b?.typeRef)
    }

    @Test
    fun `brackets of single value treated as same`() {
        val ast = yaflBuild(
                "fun main() => 1 * (2 + 3)\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `conditional expression`() {
        val ast = yaflBuild(
                "fun main() => (1 == 1) ? 1 : 2\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `lambda parameter type is inferred`() {
        val ast = yaflBuild(
                "fun f1(a:(Int32):Int8) => 1\n" +
                "fun f2() => f1( (i) => 1i8 )\n"+
                "fun main(): Int32 => 1\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::f2" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `lambda parameter type is inferred2`() {
        val ast = yaflBuild(
                "fun test( l : (Int32):Int8 ) => Int32(l(1))\n" +
                "fun main() => test( (v)=>Int8(v) )\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `generic identity function with explicit type`() {
        val ast = yaflBuild(
                "fun genericIdentity<TValue>(genericValue: TValue): TValue => genericValue\n" +
                "fun main() => genericIdentity<Int32>(1)\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `generic identity function with implicit type`() {
        val ast = yaflBuild(
                "fun genericIdentity<TValue>(genericValue: TValue) => genericValue\n" +
                "fun main() => genericIdentity(1)\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `generic container`() {
        val ast = yaflBuild(
                "class GenericContainer<TValue>(genericValue: TValue)\n" +
                "fun main() => GenericContainer(1).genericValue\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `generic container with function`() {
        val ast = yaflBuild(
                    "class GenericContainer<TValue>(genericValue: TValue)\n" +
                    "  fun getGenericValue() => genericValue\n" +
                    "fun main() => GenericContainer(1).getGenericValue()\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }


    // TODO: Test generics on interface and implemented on class with generic param



    fun readFile(file: String): Pair<String, String> {
        return Pair(file, Ast::class.java.getResource(file)!!.readText())
    }

    fun yaflBuild(test: String): Ast {
        val namer = Namer("a")

        val ast = listOf(readFile("/system.yafl"), readFile("/string.yafl"), Pair("/test.yafl", "module Test\n\nimport System\n\n" + test + "\n"))
            .map { (file, contents) -> sourceToParseTree(contents, file) }
            .mapIndexed { index, (file, tree) -> parseToAst(namer + index, file, tree) }
            .fold(Ast()) { acc, ast -> acc + ast }
            .let { resolveTypes(it) }
            .map { inferTypes(it) }
            .map { Either.some(genericSpecialization(it)) } // Replace all generics with their specialized forms, so no more generics exists in the AST
            .map { Either.some(stringsToGlobals(it)) }
            .map { Either.some(lambdaToClass(it)) }

        ast.map {
            Either.some(convertToIntermediate(it))
        }

        when (ast) {
            is Either.Some -> return ast.value
            is Either.Error -> throw Exception(ast.error.joinToString(", "))
        }
    }
}