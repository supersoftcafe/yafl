
import org.antlr.v4.runtime.CharStreams
import org.antlr.v4.runtime.CommonTokenStream
import org.junit.Test
import yafl.ast.AstProject
import yafl.ast.parseTreeToAstFile
import yafl.ir.astToIr

class ParserGeneratorTest {

    @Test fun test01() = parse("/01_hello_world.yafl")
    @Test fun test02() = parse("/02_call_function.yafl")

    private fun parse(name: String) {
        val text = yaflLexer::class.java.getResource(name)!!.readText()
        val lexer = yaflLexer(CharStreams.fromString(text))
        val parser = yaflParser(CommonTokenStream(lexer))
        val root = parser.root()
        val astFile = parseTreeToAstFile(root)
        val project = AstProject(listOf(astFile))
        val ir = astToIr(project)
        val c = yafl.ir.irToC(ir)

        println(astFile)
        println(ir)
        println(c)
    }
}