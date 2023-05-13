
import com.supersoftcafe.yafl.antlr.*
import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.codegen.generateLlvmIr
import com.supersoftcafe.yafl.codegen.optimizeLlvmIr
import com.supersoftcafe.yafl.parsetoast.parseToAst
import com.supersoftcafe.yafl.translate.*
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.Namer
import org.antlr.v4.runtime.*
import java.io.File
import kotlin.system.exitProcess


fun sourceToParseTree(contents: String, file: String): YaflParser.RootContext {
    System.err.println("Reading file $file")
    val lexer = YaflLexer(CharStreams.fromString(contents))
    val tokenStream = CommonTokenStream(lexer)
    val parser = YaflParser(tokenStream)
    return parser.root()
}


fun expandFilesList(files: List<File>): List<File> {
    return files.flatMap { file ->
        if (file.isDirectory)
             expandFilesList(file.listFiles().toList())
        else listOf(file)
    }
}


fun yaflBuild(files: List<File>): Either<String, List<String>> {
    val yaflFiles = files.filter { it.extension == "yafl" }
    val llFiles = files.filter { it.extension == "ll" }

    val namer = Namer("a")
    val ast = yaflFiles
            // Parse
//        .map { file -> Pair(file, Ast::class.java.getResource(file)!!.readText()) }
        .map { file -> file.toString() to file.readText() }
        .map { (file, contents) -> Pair(file, sourceToParseTree(contents, file)) }
        .mapIndexed { index, (file, tree) -> parseToAst(namer + index, file, tree) }
        .fold(Ast()) { acc, ast -> acc + ast }
        .let { parseErrorScan(it) }

            // Inference
        .map { resolveTypes(it) }
        .map { inferTypes(it) }

            // Lowering
        .map { Either.some(genericSpecialization(it)) } // Replace all generics with their specialized forms, so no more generics exists in the AST
        .map { Either.some(stringsToGlobals(it)) }
        .map { Either.some(lambdaToClass(it)) }

            // Emit
        .map { Either.some(convertToIntermediate(it)) }
        .map { generateLlvmIr(it.reversed()) }
        .map { Either.some(addCommonCode(it, llFiles)) }
//        .map { optimizeLlvmIr(it) }

    return ast
}

fun addCommonCode(it: String, llFiles: List<File>): String {
    return llFiles.fold(it) { acc, file -> file.readText() + acc }
}


fun main(args: Array<String>) {
    // val ast = yaflBuild("/system.yafl", "/string.yafl", "/interop.yafl", "/io.yafl", "/array.yafl")
    // val ast = yaflBuild("/system.yafl", "/string.yafl", "/test.yafl")
    val ast = yaflBuild(expandFilesList(args.map { File(it) }))
    when (ast) {
        is Either.Some -> {
            System.out.println(ast.value)
            exitProcess(0)
        }

        is Either.Error -> {
            for (e in ast.error)
                System.err.println(e)
            exitProcess(1)
        }
    }
}
