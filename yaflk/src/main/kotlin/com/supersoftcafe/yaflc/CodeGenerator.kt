package com.supersoftcafe.yaflc

import com.supersoftcafe.yaflc.llvm.*

class CodeGenerator(val ast: Ast) {
    companion object {
        const val validFirstCharacters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_."
        const val validFollowingCharacters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_.0123456789"
    }

    val structures = mutableListOf<IrStruct>()
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
                is Declaration.Struct -> decl.toIrType()
                else -> TODO("Declaration ${declaration} not supported yet")
            }
            is Type.Function -> TODO("Function type not supported yet")
            is Type.Tuple -> IrTuple(fields.map { it.type!!.toIrType() })
        }
        return result
    }

    fun Declaration.Struct.toIrType(): IrType {
        val result = stuff.filterIsInstance<IrStruct>().first()
        return result
    }

    fun Declaration.Variable.toIrVariable(): IrVariable {
        val result = stuff.filterIsInstance<IrVariable>().first()
        return result
    }


    fun Declaration.Function.toIrFunction(): IrFunction {
        val result = stuff.filterIsInstance<IrFunction>().first()
        return result
    }



    fun generateExpressionLiteralInteger(
        expression: Expression.LiteralInteger,
        function: IrFunction
    ): IrResult {
        return IrValue(expression.value.toString(), expression.type!!.toIrType())
    }

    fun generateExpressionLiteralBool(
        expression: Expression.LiteralBool,
        function: IrFunction
    ): IrResult {
        return IrValue(if (expression.value) "1" else "0", IrPrimitive.Bool)
    }

    fun generateExpressionLoadVariable(
        expression: Expression.LoadVariable,
        function: IrFunction
    ): IrResult {
        val result = function.nextRegister(expression.type!!.toIrType())
        when (val target = expression.variable) {
            is Declaration.Variable -> {
                val variable = target.toIrVariable()
                val kind = if (target.global) '@' else '%'
                function.body += "  $result = load ${result.type}, ${variable.type}* $kind${variable.name}"
            }
            else -> TODO("Unsupported load target")
        }
        return result
    }


    fun generateExpressionCallBuiltin(
        expression: Expression.Call,
        kind: BuiltinOpKind,
        function: IrFunction
    ): IrResult {
        val children = expression.children[1].expression.children

        fun llvmIntegerBinOp(op: String, type: IrType): IrResult {
            val inputResults = children.map { generateExpression(it.expression, function) }
            val inputs = inputResults.joinToString(", ") { it.toString() }
            val result = function.nextRegister(type)
            function.body += "  $result = $op ${type.llvmType} $inputs"
            return result
        }

        return when (kind) {
            BuiltinOpKind.ADD_I8  -> llvmIntegerBinOp("add", IrPrimitive.Int32)
            BuiltinOpKind.ADD_I16 -> llvmIntegerBinOp("add", IrPrimitive.Int32)
            BuiltinOpKind.ADD_I32 -> llvmIntegerBinOp("add", IrPrimitive.Int32)
            BuiltinOpKind.ADD_I64 -> llvmIntegerBinOp("add", IrPrimitive.Int64)
            BuiltinOpKind.MUL_I32 -> llvmIntegerBinOp("mul", IrPrimitive.Int32)
            BuiltinOpKind.SUB_I32 -> llvmIntegerBinOp("sub", IrPrimitive.Int32)
            BuiltinOpKind.EQU_I32 -> llvmIntegerBinOp("icmp eq", IrPrimitive.Int32)
            else -> TODO("Builtin Op ${kind} not implemented yet")
        }
    }

    fun generateExpressionCallStatic(
        expression: Expression.Call,
        target: Declaration.Function,
        function: IrFunction
    ): IrResult {
        val inputResults = expression.children[1].expression.children.map {
            generateExpression(it.expression, function)
        }
        val inputs = inputResults.joinToString(", ") {
            "${it.type} $it"
        }
        val targetAsIrFunction = target.toIrFunction()
        val result = function.nextRegister(expression.type!!.toIrType())
        function.body += "  $result = call ${result.type} @${targetAsIrFunction.name}($inputs)"
        return result
    }

    fun generateExpressionCall(
        expression: Expression.Call,
        function: IrFunction
    ): IrResult {
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
    ): IrResult {
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

        val result = function.nextRegister(expression.type!!.toIrType())
        function.body += "${endLabel.name}:"
        function.body += "  %${result.name} = phi ${result.type} [ $trueResult, %${trueLabel.name} ], [ $falseResult, %${falseLabel.name} ]"

        return result
    }

    fun generateExpressionStoreVariable(
        expression: Expression.StoreVariable,
        function: IrFunction
    ): IrResult {
        val kind = if (expression.variable!!.global) '@' else '%'
        val variable = expression.variable.toIrVariable()
        val result = generateExpression(expression.children[0].expression, function)
        function.body += "  store ${variable.type} $result, ${variable.type}* $kind${variable.name}"
        return generateExpression(expression.children[1].expression, function)
    }

    fun generateExpressionDeclareLocal(
        expression: Expression.DeclareLocal,
        function: IrFunction
    ): IrResult {
        for (declaration in expression.declarations) {
            when (declaration) {
                is Declaration.Variable -> {
                    val type = declaration.type!!.toIrType()
                    val variable = function.nextVariable2(type)
                    declaration.stuff += variable

                    function.preamble += "  %${variable.name} = alloca ${variable.type}"
                    val variableValue = generateExpression(declaration.body!!.expression, function)
                    function.body += "  store $type $variableValue, $type* %${variable.name}"
                }
                else -> throw IllegalArgumentException("${declaration::class.simpleName}")
            }
        }
        return generateExpression(expression.children.last().expression, function)
    }

    fun generateExpressionLoadField(
        expression: Expression.LoadField,
        function: IrFunction
    ): IrResult {
        val base = expression.children[0].expression
        fun loadTupleField(type: IrType, fields: List<IrType>): IrResult {
            val resultType = fields[expression.fieldIndex!!]
            val tupleValue = generateExpression(base, function)
            val result = function.nextRegister(resultType)
            function.body += "  $result = extractvalue $type $tupleValue, ${expression.fieldIndex}"
            return result
        }
        fun loadObjectField(type: IrStruct): IrResult {
            val objectValue = generateExpression(base, function)
            val fieldType = expression.type!!.toIrType()
            val fieldPtr = function.nextRegister(fieldType)
            val result = function.nextRegister(fieldType)
            function.body += "  $fieldPtr = getelementptr %${type.name}, %${type.name}* $objectValue, i32 0, i32 ${expression.fieldIndex}"
            function.body += "  $result = load $fieldType, $fieldType* $fieldPtr"
            return result
        }
        return when (val type = base.type!!.toIrType()) {
            is IrTuple ->
                loadTupleField(type, type.fields)
            is IrStruct ->
                if (type.onHeap)
                    loadObjectField(type)
                else
                    loadTupleField(type, type.getTuple().fields)
            else ->
                throw IllegalStateException("${type::class.simpleName} not supported by LoadField")
        }
    }

    fun generateExpressionTuple(
        expression: Expression.Tuple,
        function: IrFunction
    ): IrResult {
        val type = expression.type!!.toIrType() as IrTuple
        val result = expression.children.foldIndexed(IrValue("undef", type) as IrResult) { index, previous, next ->
            val value = generateExpression(next.expression, function)
            val temp = function.nextRegister(type)
            function.body += "  $temp = insertvalue $type $previous, ${type.fields[index].llvmType} $value, $index"
            temp
        }
        return result
    }

    fun generateExpressionNew(
        expression: Expression.New,
        function: IrFunction
    ): IrResult {
        fun newTuple(type: IrType, fields: List<IrType>): IrResult {
            return expression.children.foldIndexed(IrValue("undef", type) as IrResult) { index, previous, next ->
                val value = generateExpression(next.expression, function)
                val temp = function.nextRegister(type)
                function.body += "  $temp = insertvalue $type $previous, ${fields[index].llvmType} $value, $index"
                temp
            }
        }
        fun newObject(type: IrStruct): IrResult {
            val baseName = type.name.removePrefix("type_")

            val  sizep = function.nextRegister(IrPrimitive.Pointer)
            val   size = function.nextRegister(IrPrimitive.Int32)
            val vtable = function.nextRegister(IrPrimitive.Pointer)
            val    tmp = function.nextRegister(IrPrimitive.Pointer)
            val objekt = function.nextRegister(type)

            function.body += "  $sizep = getelementptr %${type.name}, %${type.name}* null, i32 1"
            function.body += "  $size = ptrtoint %${type.name}* $sizep to i32"
            function.body += "  $vtable = bitcast %vttype_$baseName* @vtable_$baseName to %vtable*"
            function.body += "  $tmp = call %object* @alloc(i32 $size, %vtable* $vtable)"
            function.body += "  $objekt = bitcast %object* $tmp to %${type.name}*"

            expression.children.forEachIndexed { index, expr ->
                val value = generateExpression(expr.expression, function)
                val fieldType = expr.expression.type!!.toIrType()
                val fieldPtr = function.nextRegister(fieldType)
                function.body += "  $fieldPtr = getelementptr %${type.name}, %${type.name}* $objekt, i32 0, i32 $index"
                function.body += "  store $fieldType $value, $fieldType* $fieldPtr"
            }

            return objekt
        }
        val result = when (val type = expression.type!!.toIrType()) {
            is IrTuple ->
                newTuple(type, type.fields)
            is IrStruct ->
                if (type.onHeap)
                    newObject(type)
                else
                    newTuple(type, type.getTuple().fields)
            else ->
                throw IllegalStateException("${type::class.simpleName} not supported by operator New")
        }
        return result
    }


    fun generateExpression(
        expression: Expression,
        function: IrFunction
    ): IrResult {
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
            is Expression.LoadVariable -> generateExpressionLoadVariable(expression, function)
            is Expression.Tuple -> generateExpressionTuple(expression, function)
            is Expression.StoreVariable -> generateExpressionStoreVariable(expression, function)
            is Expression.LoadField -> generateExpressionLoadField(expression, function)
            is Expression.New -> generateExpressionNew(expression, function)
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



    fun createStructurePrototype(module: Module, declaration: Declaration.Struct) {
        val name = "type_" + (module.name + '.' + declaration.name).cleanName()
        val tuple = { IrTuple(declaration.fields.map { it.type!!.toIrType() }) }
        val struct = IrStruct(name, "%$name${if(declaration.onHeap) "*" else ""}", "_type_$name", declaration.onHeap, tuple)
        declaration.stuff += struct
        structures += struct
    }

    fun createVariablePrototype(module: Module, declaration: Declaration.Variable) {
        val type = declaration.type!!.toIrType()
        val name = "var_" + (module.name + '_' + declaration.name).cleanName() + '_' + type.simpleName
        val variable = IrVariable(name, type)

        declaration.stuff += variable
        variables += variable
    }

    fun createFunctionPrototype(module: Module, declaration: Declaration.Function) {
        val result = declaration.result!!.toIrType()

        val name = if (declaration.synthetic) declaration.name
        else "fun_" + (module.name + '_' + declaration.name).cleanName() + '_' + result.simpleName + '_' + declaration.parameters.joinToString("") { it.type!!.toIrType().simpleName }
        val scope = if (declaration.synthetic) "dso_local" else "internal"

        val function = IrFunction(name, result)

        for (param in declaration.parameters)
            param.stuff += function.nextVariable2(param.type!!.toIrType())
        val parameters = function.variables.toList()

        val parametersString = parameters.joinToString(", ") { "${it.type} %${it.name}_in" }
        function.preamble += "define $scope ${function.result} @${function.name}($parametersString) {"

        for (param in parameters) {
            function.preamble += "  %${param.name} = alloca ${param.type}"
            function.body += "  store ${param.type} %${param.name}_in, ${param.type}* %${param.name}"
        }

        declaration.stuff += function
        functions += function
    }

    fun createPrototypes() {
        for (module in ast.modules) {
            for (part in module.parts) {
                for (declaration in part.declarations) {
                    when (declaration) {
                        is Declaration.Function ->  createFunctionPrototype(module, declaration)
                        is Declaration.Variable ->  createVariablePrototype(module, declaration)
                        is Declaration.Struct   -> createStructurePrototype(module, declaration)
                    }
                }
            }
        }
    }

    fun classDeleteAndVTable(struct: IrStruct): String {
        val baseName = struct.name.removePrefix("type_")

        val delName = "del_$baseName"
        val nl = System.lineSeparator()
        val del = "define internal void @$delName(${struct.llvmType} %p0) {$nl" +
                struct.getTuple().fields.mapIndexed { index, irType ->
                    if (irType is IrStruct && irType.onHeap) {
                        "  %v$index = getelementptr ${struct.llvmType}, ${struct.llvmType}* %p0, i32 0, i32 $index$nl" +
                        "  %r$index = bitcast $irType* %v$index to %object*$nl" +
                        "  call void @release(%object* %r$index)$nl"
                    } else ""
                }.joinToString("") +
                "  ret void$nl" +
                "}$nl$nl$nl"

        val vttypeName = "vttype_$baseName"
        val vttype = "%$vttypeName = type { void(${struct.llvmType})* }$nl$nl$nl"

        val vtableName = "vtable_$baseName"
        val vtable = "@$vtableName = internal global %$vttypeName {$nl" +
                "  void(${struct.llvmType})* @$delName$nl" +
                "}$nl$nl$nl"

        return del + vttype + vtable
    }

    fun writeIr() {
        for (struct in structures) {
            output.append("%${struct.name} = type ${struct.getTuple()}")
                .append(System.lineSeparator())
            if (struct.onHeap) {
                output.append(classDeleteAndVTable(struct))
            }
        }
        for (variable in variables)
            output.append("@${variable.name} = internal global ${variable.type} zeroinitializer")
                .append(System.lineSeparator())
        for (function in functions)
            output.append(function)
    }

    fun generate(): String {
        val stdlib = CodeGenerator::class.java.getResource("/stdlib.ll")!!.readText()
        output.append(stdlib)

        createPrototypes()
        generateIr()
        writeIr()

        if (functions.size != functions.distinctBy { it.name }.size)
            throw IllegalStateException("Found duplicate function in LLVM IR code")

        return output.toString()
    }
}