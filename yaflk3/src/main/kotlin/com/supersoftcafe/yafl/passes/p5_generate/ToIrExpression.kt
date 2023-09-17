package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.*
import com.supersoftcafe.yafl.models.llir.CgOp
import com.supersoftcafe.yafl.models.llir.CgTypePrimitive
import com.supersoftcafe.yafl.models.llir.CgTypeStruct
import com.supersoftcafe.yafl.models.llir.CgValue
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.tupleOf


private fun Expression.Let.toLetCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    assert(let.body != null)

    val (valueOps, valueReg) = let.body!!.toCgOps(namer + 1, globals, locals)
    val destructured = let.destructureRecursively(namer + 3, globals, valueReg)
    val newLocals = locals + destructured.map { (let, value, ops) -> let.id to tupleOf(let, value) }
    val destructureOps = destructured.flatMap { (let, value, ops) -> ops }

    val (tailOps, tailReg) = tail.toCgOps(namer + 2, globals, newLocals)

    return (valueOps + destructureOps + tailOps) to tailReg
}


private fun Expression.Call.callToCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>
): Pair<List<CgOp>, CgValue> {
    // Try to emit relatively efficient code here in order to make the LLVM IR output more readable. It won't
    // affect the final optimised output from OPT, but does make debugging the compiler easier.

    val resultReg = CgValue.Register((namer + 2).toString(), typeRef.toCgType(globals))
    val (paramOps, paramVals) = parameter.evaluateAndExtractTupleFields(namer + 1, globals, locals)

    fun writeDynamicCall(): Pair<List<CgOp>, CgValue> {
        val (cops, cresult) = callable.toCgOps(namer + 1, globals, locals)
        val op = CgOp.Call(resultReg, cresult, paramVals)
        return Pair(cops + paramOps + op, resultReg)
    }

    fun writeStaticCall(function: Declaration.Function, base: CgValue): Pair<List<CgOp>, CgValue> {
        val op = CgOp.CallStatic(resultReg, base, function.globalDataName(), paramVals)
        return Pair(paramOps + op, resultReg)
    }

    fun writeVirtualCall(function: Declaration.Function, base: CgValue): Pair<List<CgOp>, CgValue> {
        val op = CgOp.CallVirtual(resultReg, base, function.signature!!, paramVals)
        return Pair(paramOps + op, resultReg)
    }

    when (val callable = callable) {
        is Expression.LoadMember -> {
            val declaration = globals.type[(callable.base.typeRef as TypeRef.Klass).id]
            if (declaration is Declaration.Klass) {
                val member = declaration.findMember(callable.id!!, globals)
                    ?: throw IllegalStateException("Member ${callable.id} of ${declaration.name} not found")
                if (member is Declaration.Function) {
                    val (bops, bresult) = callable.base.toCgOps(namer + 1, globals, locals)
                    val (cops, cresult) = if (declaration.isInterface)
                        writeVirtualCall(member, bresult)
                    else writeStaticCall(member, bresult)
                    return Pair(bops + cops, cresult)
                }
            }
            return writeDynamicCall()
        }

        is Expression.LoadData -> {
            val dataRef = callable.dataRef
            if (dataRef is DataRef.Resolved) {
                if (dataRef.scope == Scope.Global) {
                    val data = globals.data[dataRef.id]
                    if (data is Declaration.Function) {
                        return writeStaticCall(data, CgValue.UNIT)
                    }
                }
            }
            return writeDynamicCall()
        }

        else -> {
            return writeDynamicCall()
        }
    }
}

private fun Expression.Parallel.parallelToCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>
): Pair<List<CgOp>, CgValue> {
    val id = namer.toString(parameter.fields.size)

    val blocks = parameter.fields.mapIndexed { index, field ->
        field.expression.toCgOps(namer + index, globals, locals)
    }

    val blockOps = blocks.flatMap { (ops, _) ->
        listOf(CgOp.ParallelBlock(id)) + ops
    }

    val type = CgTypeStruct(blocks.map { (_, value) -> value.type })
    val (tupleOps, result) = blocks.foldIndexed(Pair(listOf<CgOp>(), CgValue.undef(type))) { index, (ops, result), (_, value) ->
        val op = CgOp.InsertValue(namer.toString(index), result, intArrayOf(index), value)
        Pair(ops + op, op.result)
    }

    return Pair(listOf(CgOp.Fork(id)) + blockOps + CgOp.Join(id) + tupleOps, result)
}

private fun Expression.RawPointer.toRawPointerCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    val loadMember = field as Expression.LoadMember
    val (baseOps, baseReg) = loadMember.base.toCgOps(namer + 1, globals, locals)
    val klass = globals.type[(loadMember.base.typeRef as TypeRef.Klass).id] as Declaration.Klass
    val fieldIndex = klass.parameters.indexOfFirst { it.id == loadMember.id }
    val field = klass.parameters[fieldIndex]
    val result = CgValue.Register(namer.toString(0), CgTypePrimitive.POINTER)
    val gepOp = if (field.arraySize != null)
        CgOp.GetObjectFieldPtr(result, baseReg, globalTypeName(klass.name, klass.id), fieldIndex, CgValue.ZERO)
    else
        CgOp.GetObjectFieldPtr(result, baseReg, globalTypeName(klass.name, klass.id), fieldIndex)
    return Pair(baseOps + gepOp, result)
}

private fun Expression.newTupleToCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
    initializers: List<Expression>,
): Pair<List<CgOp>, CgValue> {
    val type = typeRef.toCgType(globals)
    val (ops, values) = initializers.foldIndexed<Expression, Pair<List<CgOp>, List<CgValue>>>(
        Pair(listOf(), listOf())
    ) { index, (acc_ops, acc_value), initializer ->
        val (ops, value) = initializer.toCgOps(namer + (index * 3), globals, locals)
        Pair(acc_ops + ops, acc_value + value)
    }
    val result = values.foldIndexed(Pair(ops, CgValue.undef(type))) { index, (ops, acc), value ->
        val op = CgOp.InsertValue(namer.plus(index * 3 + 2).toString(), acc, intArrayOf(index), value)
        Pair(ops + op, op.result)
    }
    return result
}

private fun Expression.Assert.toAssertCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>
): Pair<List<CgOp>, CgValue> {
    val (conditionOps, conditionReg) = condition.toCgOps(namer, globals, locals)
    val (valueOps, valueReg) = value.toCgOps(namer, globals, locals)
    return Pair(conditionOps + CgOp.Assert(conditionReg, message) + valueOps, valueReg)
}

fun Expression.toCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>
): Pair<List<CgOp>, CgValue> {
    return when (this) {
        is Expression.Characters -> TODO()
        is Expression.Float -> TODO()

        is Expression.RawPointer ->
            toRawPointerCgOps(namer, globals, locals)

        is Expression.Let ->
            toLetCgOps(namer, globals, locals)

        is Expression.Assert ->
            toAssertCgOps(namer, globals, locals)

        is Expression.ArrayLookup ->
            toArrayLookupCgOps(namer, globals, locals)

        is Expression.Tuple ->
            newTupleToCgOps(namer, globals, locals, fields.map { it.expression })

        is Expression.Lambda ->
            throw IllegalStateException("No lambda should exist here")

        is Expression.Integer -> {
            val type = typeRef.toCgType(globals)
            Pair(listOf(), CgValue.Immediate(value.toString(), type))
        }

        is Expression.Tag ->
            createTaggedContainerCgOps(namer, globals, locals)

        is Expression.When ->
            toWhenCgOps(namer, globals, locals)

        is Expression.NewKlass ->
            toNewKlassCgOps(namer, globals, locals)

        is Expression.LoadMember ->
            loadMemberToCgOps(namer, globals, locals)

        is Expression.Call ->
            callToCgOps(namer, globals, locals)

        is Expression.Parallel ->
            parallelToCgOps(namer, globals, locals)

        is Expression.Llvmir -> {
            val result = CgValue.Register((namer + 1).toString(), typeRef.toCgType(globals))
            val params = inputs.mapIndexed { index, input -> input.toCgOps(namer + 2 + index, globals, locals) }
            val op = CgOp.LlvmIr(
                result,
                pattern,
                params.map { (ops, value) -> value }
            )
            Pair(params.flatMap { (ops, value) -> ops } + op, result)
        }

        is Expression.LoadData -> {
            val type = typeRef.toCgType(globals)
            dataRef.toCgValue(type, globals, locals, namer)
        }

        is Expression.If -> {
            val type = typeRef.toCgType(globals)

            val (conditionOps, conditionResult) = condition.toCgOps(namer + 0, globals, locals)
            val (ifTrueOps, ifTrueResult) = ifTrue.toCgOps(namer + 1, globals, locals)
            val (ifFalseOps, ifFalseResult) = ifFalse.toCgOps(namer + 2, globals, locals)

            val ifTrueLabel = CgOp.Label(namer.plus(3).toString())
            val ifFalseLabel = CgOp.Label(namer.plus(4).toString())

            val ifTrueOriginLabel  = (ifTrueOps .lastOrNull { it is CgOp.Label } as? CgOp.Label) ?: ifTrueLabel
            val ifFalseOriginLabel = (ifFalseOps.lastOrNull { it is CgOp.Label } as? CgOp.Label) ?: ifFalseLabel

            val endLabel = CgOp.Label(namer.plus(5).toString())
            val result = CgValue.Register(namer.plus(6).toString(), type)

            val ops = conditionOps +
                    CgOp.Branch(conditionResult, ifTrueLabel.name, ifFalseLabel.name) +
                    ifTrueLabel +
                    ifTrueOps +
                    CgOp.Jump(endLabel.name) +
                    ifFalseLabel +
                    ifFalseOps +
                    CgOp.Jump(endLabel.name) +
                    endLabel +
                    CgOp.Phi(result, listOf(Pair(ifTrueResult, ifTrueOriginLabel.name), Pair(ifFalseResult, ifFalseOriginLabel.name)))

            Pair(ops, result)
        }
//
//        else ->
//            TODO("Operation ${this.javaClass.canonicalName} not implemented")
    }
}
