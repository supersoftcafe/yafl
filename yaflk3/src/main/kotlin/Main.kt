
import com.supersoftcafe.yafl.passes.p1_parse.parseFilesToAst
import com.supersoftcafe.yafl.passes.p2_resolve.resolveTypes
import com.supersoftcafe.yafl.passes.p3_infer.inferTypes
import com.supersoftcafe.yafl.passes.p4_optimise.optimise
import com.supersoftcafe.yafl.passes.p5_generate.generate
import com.supersoftcafe.yafl.utils.*
import java.io.File
import java.util.*
import kotlin.system.exitProcess


fun expandFilesList(files: List<File>): List<File> {
    return files.flatMap { file ->
        if (file.isDirectory)
             expandFilesList(file.listFiles()?.toList() ?: listOf())
        else listOf(file)
    }
}


fun yaflBuild(files: List<TextSource>): Either<String> {
    val yaflFiles = files.filter { it.location.path.substringAfter('.') == "yafl" }
    val   llFiles = files.filter { it.location.path.substringAfter('.') ==   "ll" }

    // TODO: Take list of Uri and String instead, so that input can come from assembly, or literal string etc.
    //       This will help make testing easier, so we can refer to in assembly system libraries an immediate literal test string.
    return parseFilesToAst(yaflFiles)
        .map(::resolveTypes)
        .map(::inferTypes)
        .map(::optimise)
        .map { generate(it, llFiles) }
}



fun main(args: Array<String>) {
    // val ast = yaflBuild("/system.yafl", "/string.yafl", "/interop.yafl", "/io.yafl", "/array.yafl")
    // val ast = yaflBuild("/system.yafl", "/string.yafl", "/test.yafl")
    val env = (System.getenv("YAFL_PATH")?.split(';') ?: Collections.emptyList())
    val files = expandFilesList((env + args).map { File(it) }).map(TextSource::fromFile)
    val result = yaflBuild(files)

    // val x = Ast::class.java.getResource("")

    when (result) {
        is Some -> {
            println(result.value)
            exitProcess(0)
        }

        is None -> {
            for (e in result.error)
                println(e)
            exitProcess(1)
        }
    }
}
