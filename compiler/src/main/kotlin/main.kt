
import org.antlr.v4.runtime.CharStreams
import org.antlr.v4.runtime.CommonTokenStream
import yaflParser.*


fun main(args: Array<String>) {
    val text = yaflLexer::class.java.getResource("/test.yafl")!!.readText()
    val lexer = yaflLexer(CharStreams.fromString(text))
    val parser = yaflParser(CommonTokenStream(lexer))
    val root = parser.root()
}
