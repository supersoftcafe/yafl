
import util.*
import model.*
import org.antlr.v4.runtime.CharStreams
import org.antlr.v4.runtime.CommonTokenStream
import yaflParser.*


fun main(args: Array<String>) {
    val text = Type::class.java.getResource("/test.yafl").readText()
    val lexer = yaflLexer(CharStreams.fromString(text))
    val parser = yaflParser(CommonTokenStream(lexer))
    val root = parser.root()


    val code = root
        .toImf()
        .deriveTypes()
        .generateCode()

    println(code)
}



fun RootContext.toImf(): imf.Imf {
    fun toParameter(parameterContext: ParameterContext): imf.Function {
        TODO()
    }

    fun TypeContext.toImfType(): imf.Type {
        val named = named() ?: TODO()
        return when (named.NAME().text) {
            "int" -> imf.Primitive.INT32
            "long" -> imf.Primitive.INT64
            "float" -> imf.Primitive.FLOAT32
            "double" -> imf.Primitive.FLOAT64
            else -> TODO()
        }
    }

    fun ExpressionContext.toExpression(): imf.Operation {
        return when (this) {
            is IntegerExpressionContext -> {
                val value = java.lang.Long.decode(INTEGER().text)
                if (value >= Integer.MIN_VALUE && value <= Integer.MAX_VALUE)
                    imf.Operation.ConstInt32(value.toInt())
                else
                    imf.Operation.ConstInt64(value)
            }
            is AddExpressionContext -> {
                val op = when (ADDSUB().text) {
                    "+" -> imf.BinaryOpType.ADD
                    else -> imf.BinaryOpType.SUB
                }
                imf.Operation.Binary(op, expression(0).toExpression(), expression(1).toExpression())
            }
            is MulExpressionContext -> {
                val op = when (MULTDIV().text) {
                    "*" -> imf.BinaryOpType.MUL
                    "%" -> imf.BinaryOpType.REM
                    else -> imf.BinaryOpType.DIV
                }
                imf.Operation.Binary(op, expression(0).toExpression(), expression(1).toExpression())
            }
            is NamedValueExpressionContext -> {
                imf.Operation.LoadNamedValue(NAME().text)
            }
            is InvokeExpressionContext -> {
                imf.Operation.Invoke()
            }
            else -> throw UnsupportedOperationException()
        }
    }

    fun RootContext.toImfFunction(funContext: FunContext): imf.Function {
        val funDecl = funContext.funDecl()!!
        val funBody = funContext.funBody()!!
        val funStatements = funBody.statements().toList { it.statements() }
        val funParameters = funDecl.tuple()?.parameters().toList { it.parameters() }

        val name = funDecl.NAME().text
        val parameters = funParameters.map { toParameter(it.parameter()) }
        val type = funDecl.type()?.toImfType()

        val funcs = funStatements
            .mapNotNull { it.let() }
            .map { imf.Function(it.NAME().text, emptyList(), expression = it.expression().toExpression()) } +
                funStatements
                    .mapNotNull { it.`fun`() }
                    .map { toImfFunction(it) }

        if (funcs.any { it.parameters.isNotEmpty() })
            throw IllegalArgumentException("Nested function with parameters not supported yet")
        if (funcs.map { it.name }.toSet().count() != funcs.count())
            throw IllegalArgumentException("Duplicate locals defined")

        val expression = funBody.expression().toExpression()

        return imf.Function(name, parameters, type, locals = funcs, expression = expression)
    }

    val declarations = declarations()
        .toList { it.declarations() }

    return imf.Imf(
        functions = declarations
            .mapNotNull { it.`fun`() }
            .map { toImfFunction(it) }
    )
}


tailrec fun imf.Imf.deriveTypes(): imf.Imf {
    fun deriveTypes(function: imf.Function): imf.Function {
        function.parameters.forEach {
            if (it.parameters.isNotEmpty()) TODO("Function passing is not supported yet")
            if (it.type?.cname == null) TODO("Function parameter type resolving is not supported yet")
        }

        return function.copy(
            cname = function.cname ?: "fun_${function.name}",
            type = function.type ?: function.expression?.type,
            expression = imf.Transformers.transform(function.expression, function.type)
        )
    }

    fun deriveTypes(structure: imf.Structure): imf.Structure {
        TODO()
    }

    val result = copy(
        functions = functions.map { deriveTypes(it) },
        structures = structures.map { deriveTypes(it) })
    if (result == this) return this
    return result.deriveTypes()
}


fun imf.Imf.generateCode(): String {

    fun imf.Structure.createCStruct(): String {
        TODO("Not done yet")
    }

    fun imf.Function.toParameter(): String {
        TODO()
    }

    fun imf.Operation.toCExpression(): String {
        return when (this) {
            is imf.Operation.ConstInt32 -> "((int32_t)$value)";
            is imf.Operation.ConstInt64 -> "((int64_t)${value}L)";
            is imf.Operation.ConstFloat32 -> "((float)${value}F)";
            is imf.Operation.ConstFloat64 -> "((double)$value)";
            is imf.Operation.Binary -> {
                val infixOperator = when (op) {
                    imf.BinaryOpType.ADD -> "+"
                    imf.BinaryOpType.SUB -> "-"
                    imf.BinaryOpType.MUL -> "*"
                    imf.BinaryOpType.DIV -> "/"
                    imf.BinaryOpType.REM -> "%"
                }
                "(${left.toCExpression()}$infixOperator${right.toCExpression()})"
            }
            is imf.Operation.CastPrimitive -> {
                when (type) {
                    imf.Primitive.INT32 -> "((int32_t)${input.toCExpression()})"
                    imf.Primitive.INT64 -> "((int64_t)${input.toCExpression()})"
                    imf.Primitive.FLOAT32 -> "((float)${input.toCExpression()})"
                    imf.Primitive.FLOAT64 -> "((double)${input.toCExpression()})"
                }
            }
            is imf.Operation.LoadNamedValue -> name
            is imf.Operation.Invoke -> TODO()
        }
    }

    fun imf.Function.createCFunction(): String {
        val functionName = cname ?: throw IllegalArgumentException("Function has no cname")
        val returnType = type?.cname ?: throw IllegalArgumentException("Return type unknown")
        if (returnType != expression?.type?.cname) throw IllegalArgumentException("Return type mismatch")

        val parameters = parameters.joinToString(", ") { it.toParameter() }
        val locals =
            locals.joinToString("") { "    ${it.type?.cname} ${it.cname} = ${it.expression?.toCExpression()};" }

        return "static $returnType $functionName($parameters)\n" +
                "{\n" + locals +
                "    return ${expression.toCExpression()};\n" +
                "}\n"
    }

    fun readResource(name: String): String {
        // return Type::class.java.getResource("/${name}").readText()
        return ""
    }

    val head = readResource("head.c")
    val tail = readResource("tail.c")

    val structs = structures.map { it.createCStruct() }
    val forwardStructs = structs.map { it.split('\n')[0] + ';' }
    val funcs = functions.map { it.createCFunction() }
    val forwardFuncs = funcs.map { it.split('\n')[0] + ';' }

    val contents = (listOf(head) + forwardStructs + structs + forwardFuncs + funcs + tail).joinToString("\n")

    return contents
}
