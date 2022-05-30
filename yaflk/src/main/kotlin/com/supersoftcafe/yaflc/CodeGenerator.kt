package com.supersoftcafe.yaflc

import com.supersoftcafe.yaflc.llvm.*

class CodeGenerator(val ast: Ast) {
    companion object {
        const val validCharacters = "-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ._$"
    }

    val functions = mutableListOf<IrFunction>()
    val output = StringBuilder()


    fun String.cleanName(): String {
        val builder = StringBuilder()
        for (chr in this) {
            if (chr in validCharacters)
                builder.append(chr)
            else
                builder.append('$').append(chr.code).append("_")
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
            is Type.Tuple -> TODO("Tuple type not supported yet")
        }
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

    fun generateExpressionLoadLocalVariable(
        expression: Expression.LoadLocalVariable,
        function: IrFunction
    ): String {
        val result = when (val target = expression.variable) {
            is Declaration.Variable -> {
                val resultVariable = function.nextVariable(expression.type!!.toIrType())
                val register = target.stuff.filterIsInstance<IrVariable>().firstOrNull()
                    ?: throw NullPointerException()
                function += "  %${resultVariable.name} = load ${resultVariable.type}, ${register.type}* %${register.name}"
                "%${resultVariable.name}"
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
        val inputs = expression.children[1].expression.children.joinToString(", ") {
            generateExpression(it.expression, function)
        }
        when (kind) {
            BuiltinOpKind.ADD_I32 -> {
                val resultVariable = function.nextVariable(IrPrimitive.Int32)
                function += "  %${resultVariable.name} = add i32 $inputs"
                return "%${resultVariable.name}"
            }
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
        function += "  %${resultVariable.name} = call ${resultVariable.type} @${targetAsIrFunction.name}($inputs)"
        return "%${resultVariable.name}"
    }

    fun generateExpressionCall(
        expression: Expression.Call,
        function: IrFunction
    ): String {
        return when (val target = expression.children.first().expression) {
            is Expression.LoadBuiltin -> generateExpressionCallBuiltin(expression, target.builtinOp!!.kind, function)
            is Expression.LoadLocalVariable -> when (val variable = target.variable) {
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
        function += "  br i1 $conditionResult, label %${trueLabel.name}, label %${falseLabel.name}"

        function += "${trueLabel.name}:"
        val trueResult = generateExpression(expression.children[1].expression, function)
        function += "  br label %${endLabel.name}"

        function += "${falseLabel.name}:"
        val falseResult = generateExpression(expression.children[2].expression, function)
        function += "  br label %${endLabel.name}"

        val resultVariable = function.nextVariable(expression.type!!.toIrType())
        function += "${endLabel.name}:"
        function += "  %${resultVariable.name} = phi ${resultVariable.type} [ $trueResult %${trueLabel.name} ], [ $falseResult, %${falseLabel.name} ]"

        return "%${resultVariable.name}"
    }

    fun generateExpression(
        expression: Expression,
        function: IrFunction
    ): String {
        val result = when (expression) {
            is Expression.LiteralInteger -> generateExpressionLiteralInteger(expression, function)
            is Expression.Call -> generateExpressionCall(expression, function)
            is Expression.Condition -> generateExpressionCondition(expression, function)
            is Expression.DeclareLocal -> TODO()
            is Expression.Lambda -> TODO()
            is Expression.LiteralFloat -> TODO()
            is Expression.LiteralString -> TODO()
            is Expression.LoadBuiltin -> TODO()
            is Expression.LoadField -> TODO()
            is Expression.LoadLocalVariable -> generateExpressionLoadLocalVariable(expression, function)
            is Expression.Tuple -> TODO()
        }
        return result
    }

    fun generateFunction(declaration: Declaration.Function) {
        val function = declaration.toIrFunction()

        val result = generateExpression(declaration.body.expression, function)

        function += "  ret ${declaration.result!!.toIrType()} $result"
        function += "}"
    }

    fun generateIr() {
        for (module in ast.modules) {
            for (part in module.parts) {
                for (declaration in part.declarations) {
                    when (declaration) {
                        is Declaration.Struct -> TODO()
                        is Declaration.Variable -> TODO()
                        is Declaration.Function -> generateFunction(declaration)
                    }
                }
            }
        }
    }

    fun createFunctionPrototypes() {
        for (module in ast.modules) {
            for (part in module.parts) {
                for (declaration in part.declarations) {
                    if (declaration is Declaration.Function) {
                        val result = declaration.result!!.toIrType()

                        val name = module.name + '_' + declaration.name.cleanName() + '_' + result + declaration.parameters.joinToString("") { "_" + it.type?.toIrType().toString() }
                        val function = IrFunction(name, result)

                        for (param in declaration.parameters)
                            param.stuff += function.nextParameter(param.type!!.toIrType())
                        val parameters = function.parameters.joinToString(", ") { "${it.type} %${it.name}_in" }

                        function += "define internal ${function.result} @${function.name}($parameters) {"

                        for (param in function.parameters) {
                            function += "  %${param.name} = alloca ${param.type}"
                            function += "  store ${param.type} %${param.name}_in, ${param.type}* %${param.name}"
                        }

                        declaration.stuff += function
                        functions.add(function)
                    }
                }
            }
        }
    }

    fun writeIr() {
        for (function in functions)
            output.append(function)

        val mains = mutableListOf<Declaration.Function>()
        for (module in ast.modules) {
            for (part in module.parts) {
                for (declaration in part.declarations) {
                    if (declaration is Declaration.Function && declaration.name == "main" && declaration.result == ast.typeInt32 && declaration.parameters.isEmpty()) {
                        mains += declaration
                    }
                }
            }
        }

        if (mains.size > 1) throw Exception("Too many main methods found")
        val main = mains.firstOrNull() ?: throw Exception("No main methods found")

        val ls = System.lineSeparator()
        output.append(ls)
            .append("define dso_local i32 @main() {").append(ls)
            .append("  %r = call i32 @${main.toIrFunction().name}()").append(ls)
            .append("  ret i32 %r").append(ls)
            .append("}").append(ls)
    }

    fun generate(): String {
        createFunctionPrototypes()
        generateIr()
        writeIr()

        return output.toString()
    }
}