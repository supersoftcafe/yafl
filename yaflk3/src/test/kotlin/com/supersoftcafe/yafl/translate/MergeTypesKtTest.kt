package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.antlr.YaflLexer
import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.ast.Ast
import com.supersoftcafe.yafl.ast.Declaration
import com.supersoftcafe.yafl.ast.PrimitiveKind
import com.supersoftcafe.yafl.ast.TypeRef
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
        val ast = yaflBuild("let value = 1")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::value" }?.declaration as? Declaration.Let
        assertEquals(TypeRef.Int32, decl?.typeRef)
    }

    @Test
    fun `given an immediate constant, function is of type int`() {
        val ast = yaflBuild("fun main() => 1")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `function is used with int, so parameter type becomes int`() {
        val ast = yaflBuild("fun value(a) => a\nfun main() => value(1)\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::value" }?.declaration as? Declaration.Function
        val param_a = decl?.parameters?.firstOrNull { it.name == "a" }
        assertEquals(TypeRef.Int32, decl?.returnType)
        assertEquals(TypeRef.Int32, param_a?.typeRef)
    }

    @Test
    fun `function is used with int + int, so parameter type becomes int`() {
        val ast = yaflBuild("fun value(a, b) => a + b\nfun main() => value(1, 2)\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::value" }?.declaration as? Declaration.Function
        val param_a = decl?.parameters?.firstOrNull { it.name == "a" }
        val param_b = decl?.parameters?.firstOrNull { it.name == "b" }
        assertEquals(TypeRef.Int32, decl?.returnType)
        assertEquals(TypeRef.Int32, param_a?.typeRef)
        assertEquals(TypeRef.Int32, param_b?.typeRef)
    }

    @Test
    fun `brackets of single value treated as same`() {
        val ast = yaflBuild("fun main() => 1 * (2 + 3)\n")
        val decl = ast.declarations.firstOrNull { it.declaration.name == "Test::main" }?.declaration as? Declaration.Function
        assertEquals(TypeRef.Int32, decl?.returnType)
    }

    @Test
    fun `conditional expression`() {
        val ast = yaflBuild("fun main() => (1 = 1) ? 1 : 2\n")
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

        val ast = listOf(readFile("/system.yafl"), Pair("/test.yafl", "module Test\n\nimport System\n\n" + test + "\n"))
            .map { (file, contents) -> Pair(file, sourceToParseTree(contents)) }
            .mapIndexed { index, (file, tree) -> parseToAst(namer + index, file, tree) }
            .fold(Ast()) { acc, ast -> acc + ast }
            .let { resolveTypes(it) }
            .map { inferTypes(it) }

        when (ast) {
            is Either.Some -> return ast.value
            is Either.Error -> throw Exception(ast.error.joinToString(", "))
        }
    }
}