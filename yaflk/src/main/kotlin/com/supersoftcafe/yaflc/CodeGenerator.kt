package com.supersoftcafe.yaflc

import com.supersoftcafe.yaflc.llvm.*
import kotlinx.collections.immutable.PersistentList
import kotlinx.collections.immutable.persistentListOf

class CodeGenerator(val ast: Ast) {
    companion object {
        const val validFirstCharacters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_."
        const val validFollowingCharacters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_.0123456789"
    }

//    val interfaces = mutableListOf<IrInterface>()
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
            is Type.Function -> IrLambda(result!!.toIrType(), parameter.toIrType() as IrTuple)
            is Type.Tuple -> IrTuple(fields.map { it.type!!.toIrType() })
        }
        return result
    }

    fun Declaration.Struct.toIrType(): IrType {
        val result = stuff.filterIsInstance<IrStruct>().first()
        return result
    }

//    fun Declaration.Interface.toIrType(): IrType {
//        val result = stuff.filterIsInstance<IrInterface>().first()
//        return result
//    }

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
        val type = expression.type!!.toIrType()
        val result = function.nextRegister(type)

        when (val target = expression.variable) {
            is Declaration.Variable -> {
                val variable = target.toIrVariable()
                val kind = if (target.global) '@' else '%'

                function.body += "  $result = load ${result.type}, ${variable.type}* $kind${variable.name}"
            }

            is Declaration.Function -> {
                val targetFunc = target.toIrFunction()
                val ftype = type as IrLambda

                val temp1 = function.nextRegister(IrPrimitive.Pointer)
                val temp2 = function.nextRegister(IrPrimitive.Lambda)

                function.body += "  $temp1 = bitcast ${ftype.typeIfGlobal} @${targetFunc.name} to ${IrPrimitive.Pointer}"
                function.body += "  $temp2 = insertvalue %lambda undef, ${IrPrimitive.Pointer} $temp1, 0"
                function.body += "  $result = insertvalue %lambda $temp2, ${IrPrimitive.Object} null, 1"
            }

            else -> TODO("Unsupported load target")
        }

        return result
    }


    fun generateExpressionBuiltin(
        expression: Expression.Builtin,
        function: IrFunction
    ): IrResult {
        val op = expression.op!!
        val param = generateExpression(expression.children[0].expression, function)
        val result = function.nextRegister(expression.type!!.toIrType())
        val types = param.type as IrTuple

        fun llvmIntegerUnaryOp(op: String, type: IrPrimitive) {
            val param0 = function.nextRegister(types.fields[0])
            function.body += "  $param0 = extractvalue $types $param, 0"
            function.body += "  $result = $op $type $param0 to ${result.type}"
        }

        fun llvmIntegerBinOp(op: String, type: IrPrimitive) {
            val param0 = function.nextRegister(types.fields[0])
            val param1 = function.nextRegister(types.fields[1])
            function.body += "  $param0 = extractvalue $types $param, 0"
            function.body += "  $param1 = extractvalue $types $param, 1"
            function.body += "  $result = $op $type $param0, $param1"
        }

        when (op.kind) {
            BuiltinOpKind.CONVERT_I8_TO_I16 -> llvmIntegerUnaryOp("sext", IrPrimitive.Int16)
            BuiltinOpKind.CONVERT_I16_TO_I32 -> llvmIntegerUnaryOp("sext", IrPrimitive.Int32)
            BuiltinOpKind.CONVERT_I32_TO_I64 -> llvmIntegerUnaryOp("sext", IrPrimitive.Int64)
            BuiltinOpKind.CONVERT_F32_TO_F64 -> llvmIntegerUnaryOp("fpext", IrPrimitive.Float64)
            BuiltinOpKind.ADD_I8  -> llvmIntegerBinOp("add", IrPrimitive.Int8)
            BuiltinOpKind.ADD_I16 -> llvmIntegerBinOp("add", IrPrimitive.Int16)
            BuiltinOpKind.ADD_I32 -> llvmIntegerBinOp("add", IrPrimitive.Int32)
            BuiltinOpKind.ADD_I64 -> llvmIntegerBinOp("add", IrPrimitive.Int64)
            BuiltinOpKind.ADD_F32 -> llvmIntegerBinOp("fadd", IrPrimitive.Float32)
            BuiltinOpKind.ADD_F64 -> llvmIntegerBinOp("fadd", IrPrimitive.Float64)
            BuiltinOpKind.SUB_I8  -> llvmIntegerBinOp("sub", IrPrimitive.Int8)
            BuiltinOpKind.SUB_I16 -> llvmIntegerBinOp("sub", IrPrimitive.Int16)
            BuiltinOpKind.SUB_I32 -> llvmIntegerBinOp("sub", IrPrimitive.Int32)
            BuiltinOpKind.SUB_I64 -> llvmIntegerBinOp("sub", IrPrimitive.Int64)
            BuiltinOpKind.SUB_F32 -> llvmIntegerBinOp("fsub", IrPrimitive.Float32)
            BuiltinOpKind.SUB_F64 -> llvmIntegerBinOp("fsub", IrPrimitive.Float64)
            BuiltinOpKind.MUL_I8  -> llvmIntegerBinOp("mul", IrPrimitive.Int8)
            BuiltinOpKind.MUL_I16 -> llvmIntegerBinOp("mul", IrPrimitive.Int16)
            BuiltinOpKind.MUL_I32 -> llvmIntegerBinOp("mul", IrPrimitive.Int32)
            BuiltinOpKind.MUL_I64 -> llvmIntegerBinOp("mul", IrPrimitive.Int64)
            BuiltinOpKind.MUL_F32 -> llvmIntegerBinOp("fmul", IrPrimitive.Float32)
            BuiltinOpKind.MUL_F64 -> llvmIntegerBinOp("fmul", IrPrimitive.Float64)
            BuiltinOpKind.EQU_I8 -> llvmIntegerBinOp("icmp eq", IrPrimitive.Int8)
            BuiltinOpKind.EQU_I16 -> llvmIntegerBinOp("icmp eq", IrPrimitive.Int16)
            BuiltinOpKind.EQU_I32 -> llvmIntegerBinOp("icmp eq", IrPrimitive.Int32)
            BuiltinOpKind.EQU_I64 -> llvmIntegerBinOp("icmp eq", IrPrimitive.Int64)
            BuiltinOpKind.EQU_F32 -> llvmIntegerBinOp("fcmp oeq", IrPrimitive.Float32)
            BuiltinOpKind.EQU_F64 -> llvmIntegerBinOp("fcmp oeq", IrPrimitive.Float64)
            else -> TODO("Builtin Op ${op.kind} not implemented yet")
        }

        return result
    }

//    fun generateParameterResults(
//        tuple: Expression,
//        function: IrFunction
//    ): String {
//        val inputResults = tuple.children.flatMap {
//            val exprResult = generateExpression(it.expression, function)
//            val type = exprResult.type
//            if (it is TupleField && it.unpack && type is IrTuple) {
//                type.fields.mapIndexed { index, fieldType ->
//                    val fieldRegister = function.nextRegister(fieldType) // Always borrowed as tuple handles ownership
//                    function.body += "  $fieldRegister = extractvalue $type $exprResult, $index"
//                    Pair(fieldType, fieldRegister)
//                }
//            } else {
//                listOf(Pair(type, exprResult))
//            }
//        }
//        return inputResults.joinToString(", ") { (type, name) -> "$type $name" }
//    }

//    fun generateExpressionInterfaceCall(
//        expression: Expression.InterfaceCall,
//        function: IrFunction
//    ): IrResult {
//        val target = generateExpression(expression.children.first().expression, function)
//        val inputs = generateParameterResults(expression.children[1].expression, function)
//
//        val type = expression.type!!.toIrType()
//        val result = function.nextRegister(type, owned = type.hasObjectMembers())
//        function.body += ""
//    }

//    fun generateExpressionCallStatic(
//        expression: Expression.Call,
//        target: Declaration.Function,
//        function: IrFunction
//    ): IrResult {
//        val inputs = generateParameterResults(expression.children[1].expression, function)
//
//        val targetAsIrFunction = target.toIrFunction()
//        val type = expression.type!!.toIrType()
//        val result = function.nextRegister(type, owned = type.hasObjectMembers())
//        function.body += "  $result = call ${result.type} @${targetAsIrFunction.name}($inputs)"
//        return result
//    }

    fun generateExpressionCall(
        expression: Expression.Call,
        function: IrFunction
    ): IrResult {
        val (target, params) = expression.children.map { generateExpression(it.expression, function) }
        val ftype = target.type as IrLambda
        val types = (params.type as IrTuple).fields

        val temp1 = function.nextRegister(IrPrimitive.Pointer)
        val temp2 = function.nextRegister(IrPrimitive.Object)
        val temp3 = function.nextRegister(target.type)

        function.body += "  $temp1 = extractvalue %lambda $target, 0"
        function.body += "  $temp2 = extractvalue %lambda $target, 1"
        function.body += "  $temp3 = bitcast i8* $temp1 to ${ftype.typeIfMember}"

        val paramRegisters = types.mapIndexed { index, fieldType ->
            val tmp = function.nextRegister(fieldType)
            function.body += "  $tmp = extractvalue ${params.type} $params, $index"
            ", $fieldType $tmp"
        }.joinToString("")

        val result = function.nextRegister(expression.type!!.toIrType())
        function.body += "  $result = call ${result.type} $temp3(%object* $temp2$paramRegisters)"

        return result
    }

    fun generateExpressionCondition(
        expression: Expression.Condition,
        function: IrFunction
    ): IrResult {
        val trueLabel = function.nextLabel()
        val falseLabel = function.nextLabel()
        val endLabel = function.nextLabel()

        val conditionResult = generateExpression(expression.children[0].expression, function)
        function.body += "  br i1 $conditionResult, label %${trueLabel.name}, label %${falseLabel.name}"

        function.body += "${trueLabel.name}:"
        val trueResult = generateExpression(expression.children[1].expression, function, dontRelease = true)
        val trueBranch = function.body.size
        function.body += "  br label %${endLabel.name}"

        function.body += "${falseLabel.name}:"
        val falseResult = generateExpression(expression.children[2].expression, function, dontRelease = true)
        val falseBranch = function.body.size
        function.body += "  br label %${endLabel.name}"

        val trueOwned = trueResult is IrRegister && trueResult.owned
        val falseOwned = falseResult is IrRegister && falseResult.owned

        // Insert an extra acquire as required into the appropriate branch block
        if (falseResult is IrRegister && trueOwned && !falseOwned)
            acquireNow(function, falseResult, falseBranch)
        else if (trueResult is IrRegister && !trueOwned && falseOwned)
            acquireNow(function, trueResult, trueBranch)

        val result = function.nextRegister(expression.type!!.toIrType(), owned = trueOwned || falseOwned)
        function.body += "${endLabel.name}:"
        function.body += "  %${result.name} = phi ${result.type} [ $trueResult, %${trueLabel.name} ], [ $falseResult, %${falseLabel.name} ]"

        return result
    }

    fun generateExpressionInitGlobal(
        expression: Expression.InitGlobal,
        function: IrFunction
    ): IrResult {
        val variable = expression.variable!!
        if (!variable.global)
            throw IllegalArgumentException("InitGlobal can only be used on globals")
        val irVariable = expression.variable.toIrVariable()
        val type = irVariable.type

        val result = generateExpression(expression.children[0].expression, function, dontRelease = true)
        if (variable.global && result is IrRegister && !result.owned)
            acquireNow(function, result)
        function.body += "  store $type $result, $type* @${irVariable.name}"

        releaseLater(function, irVariable)

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
                    val variable = function.nextVariable(type)
                    declaration.stuff += variable

                    function.enter += "  %${variable.name} = alloca ${variable.type}"
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
            function.body += "  $fieldPtr = getelementptr %${type.name}, %${type.name}* $objectValue, i32 0, i32 1, i32 ${expression.fieldIndex}"
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
                    loadTupleField(type, type.tuple.fields)
            else ->
                throw IllegalStateException("${type::class.simpleName} not supported by LoadField")
        }
    }

    fun generateExpressionTuple(
        expression: Expression.Tuple,
        function: IrFunction
    ): IrResult {
        val type = expression.type!!.toIrType() as IrTuple
        val results = expression.children.map { generateExpression(it.expression, function, dontRelease = true) }
        val isOwned = results.any { it is IrRegister && it.owned }

        val result = results.foldIndexed(IrValue("undef", type) as IrResult) { index, previous, value ->
            if (isOwned && value is IrRegister && !value.owned)
                acquireNow(function, value)
            val temp = function.nextRegister(type, owned = isOwned)
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
            val results = expression.children.map { generateExpression(it.expression, function, dontRelease = true) }
            val isOwned = results.any { it is IrRegister && it.owned }

            return results.foldIndexed(IrValue("undef", type) as IrResult) { index, previous, value ->
                if (isOwned && value is IrRegister && !value.owned)
                    acquireNow(function, value)
                val temp = function.nextRegister(type, owned = isOwned)
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
            val objekt = function.nextRegister(type, owned = true)

            function.body += "  $size = ptrtoint %${type.name}* getelementptr(%${type.name}, %${type.name}* null, i32 1) to %size_t"
            function.body += "  $vtable = bitcast %vttype_$baseName* @vtable_$baseName to %vtable*"
            function.body += "  $tmp = call %object* @create_object(%size_t $size, %vtable* $vtable)"
            function.body += "  $objekt = bitcast %object* $tmp to %${type.name}*"

            expression.children.forEachIndexed { index, expr ->
                val value = generateExpression(expr.expression, function, dontRelease = true)
                if (value is IrRegister && !value.owned)
                    acquireNow(function, value)
                val fieldType = expr.expression.type!!.toIrType()
                val fieldPtr = function.nextRegister(fieldType)
                function.body += "  $fieldPtr = getelementptr %${type.name}, %${type.name}* $objekt, i32 0, i32 1, i32 $index"
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
                    newTuple(type, type.tuple.fields)
            else ->
                throw IllegalStateException("${type::class.simpleName} not supported by operator New")
        }
        return result
    }


    fun generateExpression(
        expression: Expression,
        function: IrFunction,
        dontRelease: Boolean = false
    ): IrResult {
        val result = when (expression) {
            is Expression.LiteralBool -> generateExpressionLiteralBool(expression, function)
            is Expression.LiteralInteger -> generateExpressionLiteralInteger(expression, function)
            is Expression.Call -> generateExpressionCall(expression, function)
            is Expression.Builtin -> generateExpressionBuiltin(expression, function)
            is Expression.Condition -> generateExpressionCondition(expression, function)
            is Expression.DeclareLocal -> generateExpressionDeclareLocal(expression, function)
            is Expression.Lambda -> TODO()
            is Expression.LiteralFloat -> TODO()
            is Expression.LiteralString -> TODO()
            is Expression.LoadVariable -> generateExpressionLoadVariable(expression, function)
            is Expression.Tuple -> generateExpressionTuple(expression, function)
            is Expression.InitGlobal -> generateExpressionInitGlobal(expression, function)
            is Expression.LoadField -> generateExpressionLoadField(expression, function)
            is Expression.New -> generateExpressionNew(expression, function)
            is Expression.Apply -> throw UnsupportedOperationException("Expression.Apply is not real code")
//            is Expression.InterfaceCall -> generateExpressionInterfaceCall(expression, function)
        }

        if (!dontRelease && result is IrRegister && result.owned)
            releaseLater(function, result)

        return result
    }


    fun releaseLater(function: IrFunction, register: IrRegister) {
        if (!register.owned)
            throw IllegalArgumentException("Not owned")

        releaseLater(function, register.type) { type, path ->
            if (path.isNotEmpty()) {
                val load = function.nextRegister(type)
                val pathStr = path.joinToString()
                function.body += "  $load = extractvalue ${register.type} $register, $pathStr"
                load
            } else {
                register
            }
        }

        register.owned = false
    }

    fun releaseLater(function: IrFunction, variable: IrVariable) {
        releaseLater(function, variable.type) { type, path ->
            val load = function.nextRegister(type)
            val pathStr = path.map { ", i32 $it" }.joinToString("")
            function.body += "  ${load}_ref = getelementptr ${variable.type}, ${variable.type}* @${variable.name}, i32 0$pathStr"
            function.body += "  $load = load $type, $type* ${load}_ref"
            load
        }
    }

    fun releaseLater(function: IrFunction, varType: IrType, varGet: (IrType, List<Int>) -> IrRegister) {
        fun release(type: IrType, path: PersistentList<Int>) {
            when (type) {
                is IrTuple ->
                    type.fields.forEachIndexed { index, fieldType ->
                        release(fieldType, path.add(index))
                    }
                is IrStruct ->
                    if (type.onHeap) {
                        val from = varGet(type, path)

                        val slot = function.nextRegister(from.type)
                        val load = function.nextRegister(IrPrimitive.Pointer)
                        val temp = function.nextRegister(IrPrimitive.Pointer)

                        function.enter += "  $slot = alloca ${slot.type}"
                        function.enter += "  store ${slot.type} null, ${slot.type}* $slot"

                        function.body  += "  store ${slot.type} $from, ${slot.type}* $slot"

                        function.exit += "  $load = load ${slot.type}, ${slot.type}* $slot"
                        function.exit += "  $temp = bitcast ${slot.type} $load to %object*"
                        function.exit += "  call void @release(%object* $temp)"
                    } else {
                        type.tuple.fields.forEachIndexed { index, fieldType ->
                            release(fieldType, path.add(index))
                        }
                    }
            }
        }

        release(varType, persistentListOf())
    }

    fun acquireNow(function: IrFunction, register: IrRegister, insertBefore: Int = -1) {
        var insertIndex = if (insertBefore == -1) function.body.size else insertBefore

        fun acquire(type: IrType, path: String): Boolean {
            return when (type) {
                is IrTuple -> {
                    type.fields.foldIndexed(false) { index, prev, fieldType ->
                        acquire(fieldType, "$path, $index") || prev
                    }
                }
                is IrStruct ->
                    if (type.onHeap) {
                        val from = if (path.isNotEmpty()) {
                            val load = function.nextRegister(type)
                            function.body.add(insertIndex++, "  $load = extractvalue ${register.type} $register$path")
                            load
                        } else register
                        val temp = function.nextRegister(IrPrimitive.Pointer)
                        function.body.add(insertIndex++, "  $temp = bitcast $type $from to %object*")
                        function.body.add(insertIndex++, "  call void @acquire(%object* $temp)")
                        true
                    } else {
                        type.tuple.fields.foldIndexed(false) { index, prev, fieldType ->
                            acquire(fieldType, "$path, $index") || prev
                        }
                    }
                else -> false
            }
        }

        if (register.owned)
            throw IllegalArgumentException("Already owned")
        register.owned = acquire(register.type, "")
    }

    fun generateFunction(declaration: Declaration.Function) {
        val function = declaration.toIrFunction()
        val result = generateExpression(declaration.body!!.expression, function, dontRelease = true)

        if (result is IrRegister && !result.owned)
            acquireNow(function, result)

        function.exit += "  ret ${declaration.result!!.toIrType()} $result"
        function.exit += "}"
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


//    fun createInterfacePrototype(module: Module, declaration: Declaration.Interface) {
//        val name = ("vtable_" + module.name + '.' + declaration.name).cleanName()
//
//        val prototypes = declaration.functions.mapIndexed { index, func ->
//            val result = func.result!!.toIrType()
//            val params = func.parameters.map { it.type!!.toIrType() }
//            val llvmType = "$result(%object*,${params.joinToString()})*"
//            val prototype = IrInterfaceFunction(index, llvmType, result, params)
//            prototype
//        }
//
//        val iface = IrInterface(name, "{i8*,%$name*}", "_$name", prototypes)
//        declaration.stuff += iface
//        interfaces += iface
//    }

    fun createStructurePrototype(module: Module, declaration: Declaration.Struct) {
        val name = ("type_" + module.name + '.' + declaration.name).cleanName()
        val tuple = { IrTuple(declaration.fields.map { it.type!!.toIrType() }) }
        val struct = IrStruct(name, "%$name${if(declaration.onHeap) "*" else ""}", "_$name", declaration.onHeap, tuple)
        declaration.stuff += struct
        structures += struct
    }

    fun createVariablePrototype(module: Module, declaration: Declaration.Variable) {
        val type = declaration.type!!.toIrType()
        val name = ("var_" + module.name + '_' + declaration.name).cleanName() + '_' + type.simpleName
        val variable = IrVariable(name, type)

        declaration.stuff += variable
        variables += variable
    }

    fun createFunctionPrototype(module: Module, declaration: Declaration.Function) {
        val result = declaration.result!!.toIrType()

        val name = if (declaration.synthetic) declaration.name
        else ("fun_" + module.name + '_' + declaration.name).cleanName() + '_' + result.simpleName + '_' + declaration.parameters.joinToString("") { it.type!!.toIrType().simpleName }
        //val scope = if (declaration.synthetic) "dso_local" else "internal"

        val function = IrFunction(name, result)

        for (param in declaration.parameters)
            param.stuff += function.nextVariable(param.type!!.toIrType())
        val parameters = function.variables.toList()

        val parametersString = parameters.joinToString("") { ", ${it.type} %${it.name}_in" }
        function.enter += "define internal ${function.result} @${function.name}(%object*$parametersString) {"

        for (param in parameters) {
            function.enter += "  %${param.name} = alloca ${param.type}"
            function.enter += "  store ${param.type} %${param.name}_in, ${param.type}* %${param.name}"
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
//                        is Declaration.Interface-> createInterfacePrototype(module, declaration)
                    }
                }
            }
        }
    }

    fun classDeleteAndVTable(struct: IrStruct): String {
        val baseName = struct.name.removePrefix("type_")

        val delName = "del_$baseName"
        val nl = System.lineSeparator()

        // TODO: Order these such that the most complex release happens last
        val releases = struct.tuple.fields.flatMapIndexed { index, irType ->
            if (irType is IrStruct && irType.onHeap) listOf(
                "  %v$index = getelementptr %${struct.name}, %${struct.name}* %p0, i32 0, i32 1, i32 $index",
                "  %r$index = bitcast $irType* %v$index to %object**",
                "  %x$index = load %object*, %object** %r$index",
                "  call void @release(%object* %x$index)"
            ) else listOf()
        }

        // Make sure the last call to @release comes just before the 'ret' statement so that it can tail call
        val delete = listOf("define internal void @$delName(${struct.llvmType} %p0) {") + releases.dropLast(1) + listOf(
            "  %size = ptrtoint %${struct.name}* getelementptr(%${struct.name}, %${struct.name}* null, i32 1) to %size_t",
            "  %objekt = bitcast ${struct.llvmType} %p0 to %object*",
            "  call void @delete_object(%size_t %size, %object* %objekt)"
        ) + releases.takeLast(1) + "  ret void" + "}"

        // Joint it back up to make a whole function string
        val del = delete.joinToString(nl, "", "$nl$nl$nl")

        val vttypeName = "vttype_$baseName"
        val vttype = "%$vttypeName = type { void(${struct.llvmType})* }$nl$nl$nl"

        val vtableName = "vtable_$baseName"
        val vtable = "@$vtableName = internal global %$vttypeName {$nl" +
                "  void(${struct.llvmType})* @$delName$nl" +
                "}$nl$nl$nl"

        return del + vttype + vtable
    }

//    fun interfaceVTable(iface: IrInterface): String {
//        val nl = System.lineSeparator()
//        val result = "%${iface.vtName} = type { { void(%object*)* }, { ${iface.functions.joinToString()} } }$nl$nl$nl"
//        return result
//    }

    fun writeIr() {
        val nl = System.lineSeparator()

        for (struct in structures) {
            if (struct.onHeap) {
                output.append("%${struct.name} = type { %object, ${struct.tuple} }$nl$nl")
                output.append(classDeleteAndVTable(struct))
            } else {
                output.append("%${struct.name} = type ${struct.tuple}$nl$nl")
            }
        }

//        for (iface in interfaces) {
//            output.append(interfaceVTable(iface))
//        }

        for (variable in variables) {
            output.append("@${variable.name} = internal global ${variable.type} zeroinitializer$nl$nl")
        }

        for (function in functions) {
            output.append(function)
        }
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