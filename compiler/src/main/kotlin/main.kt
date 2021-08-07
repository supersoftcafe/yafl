
import model.*
import org.antlr.v4.runtime.CharStreams
import org.antlr.v4.runtime.CommonTokenStream
import yaflParser.*
import java.math.BigInteger


fun main(args: Array<String>) {
    val text = Type::class.java.getResource("/test.yafl").readText()
    val lexer = yaflLexer(CharStreams.fromString(text))
    val parser = yaflParser(CommonTokenStream(lexer))
    val root = parser.root()


    val m = root.toImf().deriveTypes()
    val c = m.generateCode()

    println(c)
    // val model = root.toModel()
    // generateCode(model);
    // val source = model.toSource()
}





fun imf.Imf.deriveOperationType(function: imf.Function, operation: imf.Operation): List<imf.Operation> {
    return if (operation.type != null) listOf(operation) else when (operation) {
        is imf.Operation.LoadIntegerConstant -> {
            if (operation.value != BigInteger.valueOf(operation.value.toLong())) {
                throw IllegalArgumentException("Integer too big to be a long")
            } else {
                listOf(operation.copy(type = if (operation.value != BigInteger.valueOf(operation.value.toInt().toLong())) {
                    imf.Primitive.LONG
                } else {
                    imf.Primitive.INTEGER
                }))
            }
        }

        // Replace with "Invoke", where Add is a function with a generic constraint.
        is imf.Operation.Add -> {
            val leftOp  = function.operations.last { it.cname == operation.left }
            val rightOp = function.operations.last { it.cname == operation.right }

            if (leftOp.type?.cname == rightOp.type?.cname) {
                listOf(operation.copy(type = leftOp.type))
            } else if (leftOp.type == imf.Primitive.INTEGER && rightOp.type == imf.Primitive.LONG) {
                val newReg = operation.cname + "_cast_input"
                listOf(
                    imf.Operation.PromoteType(newReg, leftOp.cname, rightOp.type),
                    operation.copy(type = rightOp.type, left = newReg)
                )
            } else if (leftOp.type == imf.Primitive.LONG && rightOp.type == imf.Primitive.INTEGER) {
                val newReg = operation.cname + "_cast_input"
                listOf(
                    imf.Operation.PromoteType(newReg, rightOp.cname, leftOp.type),
                    operation.copy(type = leftOp.type, right = newReg)
                )
            } else {
                throw IllegalArgumentException("Adding different types")
            }
        }

        is imf.Operation.PromoteType -> {
            listOf(operation)
        }

        else -> TODO()
    }
}

fun imf.Imf.deriveTypes(function: imf.Function): imf.Function {
    function.parameters.forEach {
        if (it.parameters.isNotEmpty()) TODO("Function passing is not supported yet")
        if (it.type?.cname == null) TODO("Function parameter type resolving is not supported yet")
    }

    val returnType = function.type
    val opIndex = function.operations.lastIndex
    val operations = function.operations.flatMap { deriveOperationType(function, it) }
    val exprType = operations.last().type
    val cname = function.cname ?: "fun_${function.name}"
    val result = function.copy(cname = cname, type = returnType ?: exprType, operations = operations)

    return result
}

fun imf.Imf.deriveTypes(structure: imf.Structure): imf.Structure {
    TODO()
}

tailrec fun imf.Imf.deriveTypes(): imf.Imf {
    val result = copy(
        functions  = functions .map { deriveTypes(it) },
        structures = structures.map { deriveTypes(it) })
    if (result == this) return this
    return result.deriveTypes()
}








fun imf.Function.withOp(operation: imf.Operation): imf.Function {
    return copy(operations = operations + operation)
}

fun imf.Function.nextRegisterName(hint: String? = null): String {
    return "reg_${operations.count()}_${hint?:""}"
}

fun imf.Function.addOperations(expr: ExpressionContext): imf.Function {
    return when (expr) {
        is AddExpressionContext -> {
            val leftFunc = this.addOperations(expr.expression(0))
            val leftOp = leftFunc.operations.last()
            val rightFunc = leftFunc.addOperations(expr.expression(1))
            val rightOp = rightFunc.operations.last()
            rightFunc.withOp(imf.Operation.Add(
                rightFunc.nextRegisterName(),
                leftOp.cname,
                rightOp.cname
            ))
        }
        is IntegerExpressionContext -> {
            withOp(imf.Operation.LoadIntegerConstant(
                nextRegisterName(),
                BigInteger(expr.text)
            ))
        }
        else -> TODO()
    }
}

fun imf.Function.addOperations(stat: StatementsContext?): imf.Function {
    return if (stat == null) return this
    else stat.let()?.let { addOperations(it) } ?: stat.`fun`().let { addOperations(it) }
}

fun imf.Function.addOperations(stat: LetContext): imf.Function {
    TODO()
}

fun imf.Function.addOperations(stat: FunContext): imf.Function {
    TODO()
}

fun RootContext.toParameter(parameterContext: ParameterContext): imf.Function {
    TODO()
}

fun RootContext.toType(typeContext: TypeContext): imf.Type {
    val named = typeContext.named() ?: TODO()
    return when (named.NAME().text) {
        "int" -> imf.Primitive.INTEGER
        "long" -> imf.Primitive.LONG
        "float" -> imf.Primitive.FLOAT
        "double" -> imf.Primitive.DOUBLE
        else -> TODO()
    }
}

fun RootContext.toImfFunction(funContext: FunContext): imf.Function {
    val funDecl = funContext.funDecl()
    val name = funDecl.NAME().text
    val parameters = funDecl.tuple()
        ?. parameters()
        ?. flatten { it.parameters() }
        ?. map { toParameter(it.parameter()) }
        ?: emptyList()
    val type = funDecl.type()?.let { toType(it) }

    return imf.Function(name, parameters, type)
        .addOperations(funContext.funBody().statements())
        .addOperations(funContext.funBody().expression())
}

fun <T> T?.flatten(next: (T) -> T?): List<T> {
    return if (this == null) {
        emptyList()
    } else {
        listOf(this) + next(this).flatten(next)
    }
}

fun RootContext.toImf(): imf.Imf {
    return imf.Imf(
        declarations()
            .flatten { it.declarations() }
            .map { it.`fun`() }
            .filterNotNull()
            .map { toImfFunction(it) }
    )
}





fun imf.Structure.createStruct(): String {
    TODO("Not done yet")
}

fun imf.Function.toParameter(): String {
    TODO()
}

fun imf.Operation.generateCode(): String {
    val type = type ?: throw IllegalArgumentException()
    return when (this) {
        is imf.Operation.LoadIntegerConstant ->
            "    ${type.cname} $cname = $value;\n"
        is imf.Operation.Add ->
            "    ${type.cname} $cname = $left + $right;\n"
        is imf.Operation.PromoteType ->
            "    ${type.cname} $cname = (${type.cname})$input;\n"
        else -> TODO()
    }
}

fun imf.Function.createFunction(): String {
    val functionName = cname ?: throw IllegalArgumentException("Function has no cname")
    val returnType = type?.cname ?: throw IllegalArgumentException("Return type unknown")
    if (returnType != operations.last().type?.cname) throw IllegalArgumentException("Return type mismatch")

    val parameters = parameters.joinToString(", ") { it.toParameter() }
    val resultReg = operations.last().cname
    val operations = operations.joinToString("") { it.generateCode() }

    return "static $returnType $functionName($parameters)\n" +
            "{\n" + operations +
            "    return ${resultReg};\n" +
            "}\n"
}

fun readResource(name: String): String {
    return Type::class.java.getResource("/${name}").readText()
}

fun imf.Imf.generateCode(): String {
    val head = readResource("head.c")
    val tail = readResource("tail.c")

    val structs = structures.map { it.createStruct() }
    val forwardStructs = structs.map { it.split('\n')[0] + ';' }
    val funcs = functions.map { it.createFunction() }
    val forwardFuncs = funcs.map { it.split('\n')[0] + ';' }

    val contents = (listOf(head) + forwardStructs + structs + forwardFuncs + funcs + tail).joinToString("\n")

    return contents
}
