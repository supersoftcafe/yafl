
import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.models.ast.Ast
import com.supersoftcafe.yafl.passes.p5_generate.generateLlvmIr
import com.supersoftcafe.yafl.passes.p1_parse.parseToAst
import com.supersoftcafe.yafl.passes.p1_parse.sourceToParseTree
import com.supersoftcafe.yafl.passes.p1_parse.parseErrorScan
import com.supersoftcafe.yafl.passes.p2_resolve.resolveTypes
import com.supersoftcafe.yafl.passes.p3_infer.inferTypes
import com.supersoftcafe.yafl.passes.p4_optimise.genericSpecialization
import com.supersoftcafe.yafl.passes.p4_optimise.lambdaToClass
import com.supersoftcafe.yafl.passes.p4_optimise.stringsToGlobals
import com.supersoftcafe.yafl.passes.p5_generate.convertToIntermediate
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.mapList
import com.supersoftcafe.yafl.utils.some
import java.io.File
import java.util.*
import kotlin.system.exitProcess


fun expandFilesList(files: List<File>): List<File> {
    return files.flatMap { file ->
        if (file.isDirectory)
             expandFilesList(file.listFiles().toList())
        else listOf(file)
    }
}


private fun parseFile(file: File, content: String): Either<Pair<File, YaflParser.RootContext>, List<String>> {

}

private fun convertToAst(file: File, parseTree: YaflParser.RootContext): Either<Ast, List<String>> {

}



fun yaflBuild(files: List<File>): Either<String, List<String>> {
    val yaflFiles = files.filter { it.extension == "yafl" }
    val llFiles = files.filter { it.extension == "ll" }

    val namer = Namer("a")

    yaflFiles.foldIndexed(Either.some<Ast,List<String>>(Ast())) { index, acc, file ->
        readFile(file)
            .map { (file, content) -> parseFile(file, content) }
            .map { (file, parseTree) -> convertToAst(file, parseTree) }
    }


    val ast = yaflFiles
            // Parse
//        .map { file -> Pair(file, Ast::class.java.getResource(file)!!.readText()) }
        .map { file -> file.toString() to file.readText() }
        .map { (file, contents) -> sourceToParseTree(contents, file) }
        .mapIndexed { index, (file, tree) -> parseToAst(namer + index, file, tree) }
        .fold(Ast()) { acc, ast -> acc + ast }
        .let { parseErrorScan(it) }

            // Inference
        .map { resolveTypes(it) }
        .map { inferTypes(it) }

            // Lowering
        .map { some(stringsToGlobals(it)) }
        .map { some(lambdaToClass(it)) }

            // Emit
        .map { some(convertToIntermediate(it)) }
        .map { generateLlvmIr(it.reversed()) }
        .map { some(addCommonCode(it, llFiles)) }
//        .map { optimizeLlvmIr(it) }

    return ast
}

fun addCommonCode(it: String, llFiles: List<File>): String {
    return llFiles.fold(it) { acc, file -> file.readText() + acc }
}


fun main(args: Array<String>) {
    // val ast = yaflBuild("/system.yafl", "/string.yafl", "/interop.yafl", "/io.yafl", "/array.yafl")
    // val ast = yaflBuild("/system.yafl", "/string.yafl", "/test.yafl")
    val env = (System.getenv("YAFL_PATH")?.split(';') ?: Collections.emptyList())
    val ast = yaflBuild(expandFilesList((env + args).map { File(it) }))
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
