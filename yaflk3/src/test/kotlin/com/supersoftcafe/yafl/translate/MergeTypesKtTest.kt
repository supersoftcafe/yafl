package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.antlr.YaflLexer
import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.parsetoast.parseToAst
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.Namer
import org.antlr.v4.runtime.CharStreams
import org.antlr.v4.runtime.CommonTokenStream
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

internal class MergeTypesKtTest {

    @Test
    fun `given an immediate constant, let is of type int`() {
        val ast = yaflBuild(
                "let value = 1")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::value" }?.declaration as? Declaration.Let
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
                "fun f2() => f1( (i) => 1i8 )\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::f2" }?.declaration as? Declaration.Function
        val call = decl?.body as? Expression.Call
        val lambda = call?.parameter?.fields?.firstOrNull()?.expression as? Expression.Lambda
        val lambdaParam = lambda?.parameters?.firstOrNull()
        assertEquals(TypeRef.Int32, lambdaParam?.typeRef)
    }

    @Test
    fun `lambda parameter type is inferred2`() {
        val ast = yaflBuild(
                "fun test( l : (Int32):Int8 ) => Int32(l(1))\n" +
                "fun main() => test( (v)=>Int8(v) )\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        val call = decl?.body as? Expression.Call
        val lambda = call?.parameter?.fields?.firstOrNull()?.expression as? Expression.Lambda
        val lambdaParam = lambda?.parameters?.firstNotNullOfOrNull { it.typeRef }
        val lambdaResult = (lambda?.typeRef as? TypeRef.Callable)?.result
        val bodyResult = lambda?.body?.typeRef
        assertEquals(TypeRef.Int32, lambdaParam)
        assertEquals(TypeRef.Int8, lambdaResult)
        assertEquals(TypeRef.Int8, bodyResult)
    }

    @Test
    fun `generic identity function with explicit type`() {
        val ast = yaflBuild(
                "fun genericIdentity<TValue>(value: TValue) => value\n" +
                "fun main() => genericIdentity<Int32>(1)\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `generic identity function with implicit type`() {
        val ast = yaflBuild(
                "fun genericIdentity<T>(value: T) => value\n" +
                "fun main() => genericIdentity(1)\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }



    fun sourceToParseTree(contents: String): YaflParser.RootContext {
        val lexer = YaflLexer(CharStreams.fromString(contents))
        val tokenStream = CommonTokenStream(lexer)
        val parser = YaflParser(tokenStream)
        return parser.root()
    }

    fun readFile(file: String): Pair<String, String> {
        return Pair(file, Ast::class.java.getResource(file)!!.readText())
    }

    fun yaflBuild(test: String): Ast {
        val namer = Namer("a")

        val ast = listOf(readFile("/system.yafl"), readFile("/string.yafl"), Pair("/test.yafl", "module Test\n\nimport System\n\n" + test + "\n"))
            .map { (file, contents) -> Pair(file, sourceToParseTree(contents)) }
            .mapIndexed { index, (file, tree) -> parseToAst(namer + index, file, tree) }
            .fold(Ast()) { acc, ast -> acc + ast }
            .let { resolveTypes(it) }
            .map { inferTypes(it) }
//            .map { Either.some(genericSpecialization(it)) } // Replace all generics with their specialized forms, so no more generics exists in the AST
//            .map { Either.some(stringsToGlobals(it)) }
//            .map { Either.some(lambdaToClass(it)) }

        when (ast) {
            is Either.Some -> return ast.value
            is Either.Error -> throw Exception(ast.error.joinToString(", "))
        }
    }
}