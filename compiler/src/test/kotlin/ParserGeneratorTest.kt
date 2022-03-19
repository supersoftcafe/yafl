
import org.antlr.v4.runtime.CharStreams
import org.antlr.v4.runtime.CommonTokenStream
import org.junit.Test

class ParserGeneratorTest {

    @Test fun test01() = parse("/01_hello_world.yafl")
    @Test fun test02() = parse("/02_call_function.yafl")

    private fun parse(name: String) {
        val text = yaflLexer::class.java.getResource(name)!!.readText()
        val lexer = yaflLexer(CharStreams.fromString(text))
        val parser = yaflParser(CommonTokenStream(lexer))
        val root = parser.root()

        val project = yafl.ast.parseTreesToAstProject(listOf(root))
        val ir = yafl.ir.astToIr(project)
        val c = yafl.ir.irToC(ir)

        println(project)
        println(ir)
        println(c)
    }
}