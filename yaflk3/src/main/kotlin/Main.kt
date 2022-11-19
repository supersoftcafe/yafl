
import com.supersoftcafe.yafl.antlr.*
import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.codegen.generateLlvmIr
import com.supersoftcafe.yafl.codegen.optimizeLlvmIr
import com.supersoftcafe.yafl.parsetoast.addToAst
import com.supersoftcafe.yafl.tointermediate.convertToIntermediate
import com.supersoftcafe.yafl.translate.inferTypes
import com.supersoftcafe.yafl.translate.resolveTypes
import com.supersoftcafe.yafl.utils.Either
import org.antlr.v4.runtime.*


fun sourceToParseTree(contents: String): YaflParser.RootContext {
    val lexer = YaflLexer(CharStreams.fromString(contents))
    val tokenStream = CommonTokenStream(lexer)
    val parser = YaflParser(tokenStream)
    return parser.root()
}


fun yaflBuild(vararg files: String): Either<String, List<String>> {
    val ast = files
        .map { file -> Pair(file, Ast::class.java.getResource(file)!!.readText()) }
        .map { (file, contents) -> Pair(file, sourceToParseTree(contents)) }
        .fold(Ast()) { ast, (file, tree) -> addToAst(ast, file, tree) }
        .let { resolveTypes(it) }
        .map { inferTypes(it) }
        .map { convertToIntermediate(it) }
        .map { generateLlvmIr(it.reversed()) }
        .map { optimizeLlvmIr(it) }

    return ast
}




fun main(args: Array<String>) {
    val ast = yaflBuild("/system.yafl", "/test.yafl")
    when (ast) {
        is Either.Some -> {
            println("Success")
            println(ast.value)
        }

        is Either.Error -> {
            println("Failure")
            for (e in ast.error)
                println(e)
        }
    }
}
