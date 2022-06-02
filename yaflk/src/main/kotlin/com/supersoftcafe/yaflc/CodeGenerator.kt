package com.supersoftcafe.yaflc

import com.supersoftcafe.yaflc.llvm.*

class CodeGenerator(val ast: Ast) {
    companion object {
        const val validFirstCharacters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_."
        const val validFollowingCharacters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_.0123456789"
    }

    val functions = mutableListOf<IrFunction>()
    val variables = mutableListOf<IrVariable>()
    val output = StringBuilder()


    fun String.cleanName(): String {
        val builder = StringBuilder()
        var validChars = validFirstCharacters
        for (chr in this) {
            if (chr in validChars)
                builder.append(chr)
            else
                builder.append('$').append(chr.code).append("_")
            validChars = validFollowingCharacters
        }
        return builder.toString()
    }

    fun Type.toIrType(): IrType {
        val result = when (this) {
            is Type.Named -> when (val decl = declaration) {
                is Declaration.Primitive -> when (decl.kind) {
                    PrimitiveKind.Bool -> IrPrimitive.Bool
                    PrimitiveKind.Int8 -> IrPrimitive.Int8
                    PrimitiveKind.Int16 -> IrPrimitive.Int16
                    PrimitiveKind.Int32 -> IrPrimitive.Int32
                    PrimitiveKind.Int64 -> IrPrimitive.Int64
                    PrimitiveKind.Float32 -> IrPrimitive.Float32
                    PrimitiveKind.Float64 -> IrPrimitive.Float64
                }
                is Declaration.Struct -> TODO("Struct type not supported yet")
                else -> TODO("Declaration ${declaration} not supported yet")
            }
            is Type.Function -> TODO("Function type not supported yet")
            is Type.Tuple -> IrTuple(fields.map { it.type!!.toIrType() })
        }
        return result
    }

    fun Declaration.Variable.toIrVariable(): IrVariable {
        val result = stuff.filterIsInstance<IrVariable>().firstOrNull()
            ?: throw NullPointerException()
        return result
    }


    fun Declaration.Function.toIrFunction(): IrFunction {
        val result = stuff.filterIsInstance<IrFunction>().firstOrNull()
            ?: throw NullPointerException()
        return result
    }



    fun generateExpressionLiteralInteger(
        expression: Expression.LiteralInteger,
        function: IrFunction
    ): String {
        return expression.value.toString()
    }

    fun generateExpressionLiteralBool(
        expression: Expression.LiteralBool,
        function: IrFunction
    ): String {
        return if (expression.value) "1" else "0"
    }

    fun generateExpressionLoadVariable(
        expression: Expression.LoadVariable,
        function: IrFunction
    ): String {
        val result = when (val target = expression.variable) {
            is Declaration.Variable -> {
                val register = function.nextVariable(expression.type!!.toIrType())
                val variable = target.toIrVariable()
                val kind = if (target.global) '@' else '%'
                function.body += "  %${register.name} = load ${register.type}, ${variable.type}* $kind${variable.name}"
                "%${register.name}"
            }
            else -> TODO("Unsupported load target")
        }
        return result
    }


    fun generateExpressionCallBuiltin(
        expression: Expression.Call,
        kind: BuiltinOpKind,
        function: IrFunction
    ): String {
        val children = expression.children[1].expression.children

        fun llvmIntegerBinOp(op: String, type: IrType): String {
            val inputs = children.joinToString(", ") { generateExpression(it.expression, function) }
            val resultVariable = function.nextVariable(type)
            function.body += "  %${resultVariable.name} = $op ${type.llvmType} $inputs"
            return "%${resultVariable.name}"
        }

        return when (kind) {
            BuiltinOpKind.ADD_I8 -> llvmIntegerBinOp("add", IrPrimitive.Int32)
            BuiltinOpKind.ADD_I16 -> llvmIntegerBinOp("add", IrPrimitive.Int32)
            BuiltinOpKind.ADD_I32 -> llvmIntegerBinOp("add", IrPrimitive.Int32)
            BuiltinOpKind.ADD_I64 -> llvmIntegerBinOp("add", IrPrimitive.Int64)
            else -> TODO("Builtin Op ${kind} not implemented yet")
        }
    }

    fun generateExpressionCallStatic(
        expression: Expression.Call,
        target: Declaration.Function,
        function: IrFunction
    ): String {
        val inputs = expression.children[1].expression.children.joinToString(", ") {
            "${it.expression.type!!.toIrType()} ${generateExpression(it.expression, function)}"
        }
        val targetAsIrFunction = target.toIrFunction()
        val resultVariable = function.nextVariable(expression.type!!.toIrType())
        function.body += "  %${resultVariable.name} = call ${resultVariable.type} @${targetAsIrFunction.name}($inputs)"
        return "%${resultVariable.name}"
    }

    fun generateExpressionCall(
        expression: Expression.Call,
        function: IrFunction
    ): String {
        return when (val target = expression.children.first().expression) {
            is Expression.LoadBuiltin -> generateExpressionCallBuiltin(expression, target.builtinOp!!.kind, function)
            is Expression.LoadVariable -> when (val variable = target.variable) {
                is Declaration.Function -> generateExpressionCallStatic(expression, variable, function)
                else -> TODO("Can't handle function pointers yet")
            }
            else -> TODO("Can't handle function targets like this")
        }
    }

    fun generateExpressionCondition(
        expression: Expression.Condition,
        function: IrFunction
    ): String {
        val endLabel = function.nextLabel()
        val trueLabel = function.nextLabel()
        val falseLabel = function.nextLabel()

        val conditionResult = generateExpression(expression.children[0].expression, function)
        function.body += "  br i1 $conditionResult, label %${trueLabel.name}, label %${falseLabel.name}"

        function.body += "${trueLabel.name}:"
        val trueResult = generateExpression(expression.children[1].expression, function)
        function.body += "  br label %${endLabel.name}"

        function.body += "${falseLabel.name}:"
        val falseResult = generateExpression(expression.children[2].expression, function)
        function.body += "  br label %${endLabel.name}"

        val resultVariable = function.nextVariable(expression.type!!.toIrType())
        function.body += "${endLabel.name}:"
        function.body += "  %${resultVariable.name} = phi ${resultVariable.type} [ $trueResult, %${trueLabel.name} ], [ $falseResult, %${falseLabel.name} ]"

        return "%${resultVariable.name}"
    }

    fun generateExpressionStoreVariable(
        expression: Expression.StoreVariable,
        function: IrFunction
    ): String {
        val kind = if (expression.variable!!.global) '@' else '%'
        val variable = expression.variable!!.toIrVariable()
        val result = generateExpression(expression.children[0].expression, function)
        function.body += "  store ${variable.type} $result, ${variable.type}* $kind${variable.name}"
        return generateExpression(expression.children[1].expression, function)
    }

    fun generateExpressionDeclareLocal(
        expression: Expression.DeclareLocal,
        function: IrFunction
    ): String {
        for (declaration in expression.declarations) {
            when (declaration) {
                is Declaration.Variable -> {
                    val type = declaration.type!!.toIrType()
                    val variable = function.nextVariable(type)
                    val irVariable = IrVariable(variable.name, type)
                    declaration.stuff += irVariable

                    function.preamble += "  %${variable.name} = alloca ${variable.type}"
                    val expressionResult = generateExpression(declaration.body!!.expression, function)
                    function.body += "  store $type $expressionResult, $type* %${variable.name}"
                }
                else -> throw IllegalArgumentException("${declaration::class.simpleName}")
            }
        }
        return generateExpression(expression.children.last().expression, function)
    }

    fun generateExpressionTuple(
        expression: Expression.Tuple,
        function: IrFunction
    ): String {
        val type = expression.type!!.toIrType() as IrTuple
        val result = expression.children.foldIndexed("undef") { index, previous, next ->
            val value = generateExpression(next.expression, function)
            val temp = "%${function.nextVariable(type).name}"
            function.body += "  $temp = insertvalue $type $previous, ${type.fields[index].llvmType} $value, $index"
            temp
        }
        return result
    }

    fun generateExpressionDot(
        expression: Expression.Dot,
        function: IrFunction
    ): String {
        val base = expression.children[0].expression
        val tupleType = base.type!!.toIrType() as IrTuple
        val resultType = tupleType.fields[expression.fieldIndex!!]
        val tupleValue = generateExpression(base, function)
        val result = "%${function.nextVariable(resultType).name}"
        function.body += "  $result = extractvalue $tupleType $tupleValue, ${expression.fieldIndex}"
        return result
    }


    fun generateExpression(
        expression: Expression,
        function: IrFunction
    ): String {
        val result = when (expression) {
            is Expression.LiteralBool -> generateExpressionLiteralBool(expression, function)
            is Expression.LiteralInteger -> generateExpressionLiteralInteger(expression, function)
            is Expression.Call -> generateExpressionCall(expression, function)
            is Expression.Condition -> generateExpressionCondition(expression, function)
            is Expression.DeclareLocal -> generateExpressionDeclareLocal(expression, function)
            is Expression.Lambda -> TODO()
            is Expression.LiteralFloat -> TODO()
            is Expression.LiteralString -> TODO()
            is Expression.LoadBuiltin -> TODO()
            is Expression.LoadField -> TODO()
            is Expression.LoadVariable -> generateExpressionLoadVariable(expression, function)
            is Expression.Tuple -> generateExpressionTuple(expression, function)
            is Expression.StoreVariable -> generateExpressionStoreVariable(expression, function)
            is Expression.Dot -> generateExpressionDot(expression, function)
        }
        return result
    }

    fun generateFunction(declaration: Declaration.Function) {
        val function = declaration.toIrFunction()
        val result = generateExpression(declaration.body.expression, function)
        function.body += "  ret ${declaration.result!!.toIrType()} $result"
        function.body += "}"
    }

    fun generateIr() {
        for (module in ast.modules) {
            for (part in module.parts) {
                for (declaration in part.declarations) {
                    if (declaration is Declaration.Function) {
                        generateFunction(declaration)
                    }
                }
            }
        }
    }

    fun createVariablePrototypes() {
        for (module in ast.modules) {
            for (part in module.parts) {
                for (declaration in part.declarations) {
                    if (declaration is Declaration.Variable) {
                        val type = declaration.type!!.toIrType()
                        val name = "var_" + (module.name + '_' + declaration.name).cleanName() + '_' + type.simpleName
                        val variable = IrVariable(name, type)

                        declaration.stuff += variable
                        variables += variable
                    }
                }
            }
        }
    }

    fun createFunctionPrototype(module: Module, result: IrType, declaration: Declaration.Function) {
        val name = if (declaration.synthetic) declaration.name
        else "fun_" + (module.name + '_' + declaration.name).cleanName() + '_' + result.simpleName + '_' + declaration.parameters.joinToString("") { it.type!!.toIrType().simpleName }
        val scope = if (declaration.synthetic) "dso_local" else "internal"

        val function = IrFunction(name, result)

        for (param in declaration.parameters)
            param.stuff += function.nextParameter(param.type!!.toIrType())
        val parameters = function.parameters.joinToString(", ") { "${it.type} %${it.name}_in" }

        function.preamble += "define $scope ${function.result} @${function.name}($parameters) {"

        for (param in function.parameters) {
            function.preamble += "  %${param.name} = alloca ${param.type}"
            function.body += "  store ${param.type} %${param.name}_in, ${param.type}* %${param.name}"
        }

        declaration.stuff += function
        functions += function
    }

    fun createFunctionPrototypes() {
        for (module in ast.modules) {
            for (part in module.parts) {
                for (declaration in part.declarations) {
                    if (declaration is Declaration.Function) {
                        createFunctionPrototype(module, declaration.result!!.toIrType(), declaration)
                    }
                }
            }
        }
    }

    fun writeIr() {
        for (variable in variables)
            output.append("@${variable.name} = internal global ${variable.type} zeroinitializer")
                .append(System.lineSeparator())
        for (function in functions)
            output.append(function)
    }

    fun generate(): String {
        createFunctionPrototypes()
        createVariablePrototypes()
//        createInitFunction()
        generateIr()
        writeIr()

        return output.toString()
    }
}