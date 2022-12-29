package com.supersoftcafe.yaflc.asttoir

import com.supersoftcafe.yaflc.*
import com.supersoftcafe.yaflc.codegen.*


private fun CgValue.extractAllTuple(
    operations: List<CgOp>
): Tuple2<List<CgOp>, List<CgValue>> {
    return (type as CgTypeStruct).fields
        .foldIndexed(tupleOf(operations, listOf<CgValue>())) { index, (ops, vals), type ->
            val extractValueOp = CgOp.ExtractValue("r${ops.size}", this, intArrayOf(index))
            tupleOf(ops + extractValueOp, vals + extractValueOp.result)
        }
}

private fun ExpressionRef.generateOpCodes(
    operations: List<CgOp>,
    findVal: (Declaration.Variable) -> CgValue
): Tuple2<List<CgOp>, CgValue> {
    return expression.generateOpCodes(operations, findVal)
}

private fun ExpressionRef.unpackValues(
    operations: List<CgOp>,
    findVal: (Declaration.Variable) -> CgValue
): Tuple2<List<CgOp>, List<CgValue>> {
    val (ops, tupleVal) = generateOpCodes(operations, findVal)
    return if (this is TupleField && unpack && tupleVal.type is CgTypeStruct) {
        tupleVal.extractAllTuple(ops)
    } else {
        tupleOf(ops, listOf(tupleVal))
    }
}

private fun Expression.generateOpCodes(
    operations: List<CgOp>,
    findVal: (Declaration.Variable) -> CgValue
): Tuple2<List<CgOp>, CgValue> {
    val cgType = type!!.toCgType()

    fun doTuple(children: List<ExpressionRef>) = operations
        .let { ops ->
            children.fold(tupleOf(ops, listOf<CgValue>())) { (ops, values), child ->
                child.unpackValues(ops, findVal).let { (ops, values2) ->
                    tupleOf(ops, values + values2) } } }
        .let { (ops, values) ->
            values.foldIndexed(tupleOf(ops, CgValue.Immediate("undef", cgType) as CgValue)) { index, (ops, tupleVal), value ->
                CgValue.Register("r${ops.size}", cgType).let { reg ->
                    tupleOf(ops + CgOp.InsertValue(reg, tupleVal, intArrayOf(index), value), reg) } } }

    return when (this) {
        is Expression.LiteralInteger -> {
            tupleOf(operations, CgValue.Immediate(value.toString(), cgType))
        }

        is Expression.LiteralBool -> {
            tupleOf(operations, CgValue.Immediate(if (value) "1" else "0", cgType))
        }

        is Expression.LiteralFloat -> {
            tupleOf(operations, CgValue.Immediate(value.toString(), cgType))
        }

        is Expression.LoadVariable -> {
            val variable = variable // Because 'variable' is mutable it can't smart cast
            when {
                variable is Declaration.Function -> {
                    val reg = CgValue.Register("r${operations.size}", cgType)
                    val op = CgOp.LoadStaticCallable(reg, CgValue.Global("global_unit", CgTypePrimitive.OBJECT), variable.asLlvmName())
                    tupleOf(operations + op, reg)
                }
                variable is Declaration.Variable && variable.global -> {
                    val reg = CgValue.Register("r${operations.size}", cgType)
                    val op = CgOp.Load(reg, CgValue.Global(variable.asLlvmName(), CgTypePointer(cgType)))
                    tupleOf(operations + op, reg)
                }
                variable is Declaration.Variable && !variable.global -> {
                    tupleOf(operations, findVal(variable as Declaration.Variable))
                }
                else -> {
                    throw IllegalStateException();
                }
            }
        }

        is Expression.DeclareLocal -> {
            val (ops, vars) = declarations.filterIsInstance<Declaration.Variable>()
                .fold(tupleOf(operations, mapOf<Declaration.Variable, CgValue>())) { (ops, vars), decl ->
                    val (tmpOps, tmpVal) = decl.body!!.expression.generateOpCodes(ops, findVal)
                    tupleOf(tmpOps, vars + Pair(decl, tmpVal))
                }
            children[0].expression.generateOpCodes(ops) { vars[it] ?: findVal(it) }
        }

        is Expression.Tuple -> doTuple(children)

        is Expression.Call -> {
            operations
                .let { ops -> children[0].generateOpCodes(ops, findVal) }
                .let { (ops, method) -> children[1].generateOpCodes(ops, findVal) + tupleOf(method) }
                .let { (ops, tupleVal, method) -> tupleVal.extractAllTuple(ops) + tupleOf(method) }
                .let { (ops, params, method) ->
                    val result = CgValue.Register("r${ops.size}", cgType)
                    val cgOp = CgOp.Call(result, method, params)
                    tupleOf(ops + cgOp, result)
                }
        }

        is Expression.Builtin -> {
            operations
                .let { ops -> children[0].generateOpCodes(ops, findVal) }
                .let { (ops, tupleVal) -> tupleVal.extractAllTuple(ops) }
                .let { (ops, params) ->
                    val result = CgValue.Register("r${ops.size}", cgType)
                    val cgOp = when (op!!.kind) {
                        BuiltinOpKind.ADD_I8, BuiltinOpKind.ADD_I16, BuiltinOpKind.ADD_I32, BuiltinOpKind.ADD_I64 ->
                            CgOp.Binary(result, CgBinaryOp.ADD, params[0], params[1])
                        BuiltinOpKind.ADD_F32, BuiltinOpKind.ADD_F64 ->
                            CgOp.Binary(result, CgBinaryOp.FADD, params[0], params[1])
                        else ->
                            throw IllegalArgumentException("Unknown op ${op.kind}")
                    }
                    tupleOf(ops + cgOp, result)
                }
        }

        is Expression.Condition -> {
            val  trueLabel = "l${operations.size}t"
            val falseLabel = "l${operations.size}f"
            val   endLabel = "l${operations.size}e"

            operations
                .let { ops -> children[0].generateOpCodes(ops, findVal).let { (ops, reg) -> ops + CgOp.Branch(reg, trueLabel, falseLabel) } }
                .let { ops -> children[1].generateOpCodes(listOf(CgOp.Label(trueLabel)) + ops, findVal).let { (ops, reg) ->  tupleOf(ops + CgOp.Jump(endLabel), reg) } }
                .let { (ops, ifTrue) -> children[2].generateOpCodes(listOf(CgOp.Label(falseLabel)) + ops, findVal).let { (ops, reg) -> tupleOf(ops + CgOp.Jump(endLabel), ifTrue, reg) } }
                .let { (ops, ifTrue, ifFalse) ->
                    val reg = CgValue.Register("r${ops.size}", cgType)
                    tupleOf(ops + CgOp.Label(endLabel) + CgOp.Phi(reg, listOf(ifTrue to trueLabel, ifFalse to falseLabel)), reg)
                }
        }

        is Expression.LoadField -> {
            val (ops, pointer) = children[0].generateOpCodes(operations, findVal)
            val reg = CgValue.Register("r${ops.size}", cgType)
            val llvmName = ((children[0].expression.type as Type.Named).declaration as Declaration.Struct).asLlvmName()
            val op = CgOp.GetObjectFieldPtr(reg, pointer, llvmName, this.fieldIndex!!)
            tupleOf(ops + op, reg)
        }

        is Expression.New -> {
            val struct = (type as Type.Named).declaration as Declaration.Struct
            if (struct.onHeap) {
                val llvmName = struct.asLlvmName()
                val objectPointer = CgValue.Register("r${operations.size}", CgTypePrimitive.OBJECT)
                tupleOf(children
                    .foldIndexed(operations + CgOp.New(objectPointer, llvmName)) { index, ops, exprRef ->
                        val (ops2, value) = generateOpCodes(ops, findVal)
                        val tmpReg = CgValue.Register("r${ops2.size}", CgTypePointer(value.type))
                        ops2 + CgOp.GetObjectFieldPtr(tmpReg, objectPointer, llvmName, index) + CgOp.Store(value.type, tmpReg, value)
                    }, objectPointer)
            } else {
                doTuple(children)
            }
        }

        is Expression.InitGlobal -> {
            val global = CgValue.Global(variable!!.asLlvmName(), variable!!.type!!.toCgType())
            val (ops1, value1) = children[0].generateOpCodes(operations, findVal)
            val (ops2, value2) = children[1].generateOpCodes(ops1, findVal)
            val store = CgOp.Store(global.type, global, value1)
            tupleOf(ops2 + store, value2)
        }

        else -> {
            throw IllegalArgumentException("Unknown op $javaClass")
        }
    }
}

fun generateFunction(module: Module, function: Declaration.Function): List<CgThingFunction> {
    val returnType = function.result!!.toCgType()
    val parameters = function.parameters
        .mapIndexed { index, param -> Pair(index, param) }
        .associate { (index, param) -> Pair(param, CgValue.Register("p$index", param.type!!.toCgType())) }

    val (body, value) = function.body!!.generateOpCodes(listOf(), parameters::getValue)

    return listOf(
        CgThingFunction(
            function.asLlvmName(),
            returnType,
            parameters.values.toList(),
            *(body + CgOp.Return(value)).toTypedArray()
        )
    )
}