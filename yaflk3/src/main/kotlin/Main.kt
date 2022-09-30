
import com.supersoftcafe.yafl.antlr.*
import org.antlr.v4.runtime.*
import org.antlr.v4.runtime.tree.*

fun yaflParser(file: String): YaflParser.RootContext {
    val lexer = YaflLexer(CharStreams.fromString(file))
    val tokenStream = CommonTokenStream(lexer)
    val parser = YaflParser(tokenStream)

    return parser.root()
}




fun yaflBuild(files: Map<String, String>): String {

}




fun main(args: Array<String>) {
    println("Hello World!")

    // Try adding program arguments via Run/Debug configuration.
    // Learn more about running applications: https://www.jetbrains.com/help/idea/running-applications.html.
    println("Program arguments: ${args.joinToString()}")
}