
import com.supersoftcafe.yafl.antlr.*
import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.codegen.generateLlvmIr
import com.supersoftcafe.yafl.codegen.optimizeLlvmIr
import com.supersoftcafe.yafl.parsetoast.parseToAst
import com.supersoftcafe.yafl.translate.*
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.Namer
import org.antlr.v4.runtime.*


fun sourceToParseTree(contents: String, file: String): YaflParser.RootContext {
    println("Reading file $file")
    val lexer = YaflLexer(CharStreams.fromString(contents))
    val tokenStream = CommonTokenStream(lexer)
    val parser = YaflParser(tokenStream)
    return parser.root()
}


fun yaflBuild(vararg files: String): Either<String, List<String>> {
    val namer = Namer("a")
    val ast = files
            // Parse
        .map { file -> Pair(file, Ast::class.java.getResource(file)!!.readText()) }
        .map { (file, contents) -> Pair(file, sourceToParseTree(contents, file)) }
        .mapIndexed { index, (file, tree) -> parseToAst(namer + index, file, tree) }
        .fold(Ast()) { acc, ast -> acc + ast }
        .let { parseErrorScan(it) }

            // Inference
        .map { resolveTypes(it) }
        .map { inferTypes(it) }

            // Lowering
        .map { Either.some(stringsToGlobals(it)) }
        .map { Either.some(lambdaToClass(it)) }

            // Emit
        .map { Either.some(convertToIntermediate(it)) }
        .map { generateLlvmIr(it.reversed()) }
        .map { optimizeLlvmIr(it) }
      //  .map { compileLlvmIr(it) }

    return ast
}




fun main(args: Array<String>) {
    val ast = yaflBuild("/system.yafl", "/string.yafl", "/interop.yafl", "/io.yafl", "/array.yafl")
    // val ast = yaflBuild("/system.yafl", "/lambda.yafl")
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
