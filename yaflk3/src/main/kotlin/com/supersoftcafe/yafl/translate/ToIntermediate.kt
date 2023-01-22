package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.codegen.*
import com.supersoftcafe.yafl.utils.*



private class Globals(val type: Map<Namer, Declaration.Type>, val data: Map<Namer, Declaration.Data>)

private fun localName(name: String, id: Namer) = "l$$name$$id"
private fun Declaration.Data.globalDataName() = "d$${signature!!}$$id"
private fun globalTypeName(name: String, id: Namer) = "t$$name$$id"


private fun DataRef?.toCgValue(type: CgType, globals: Globals, locals: Map<Namer, Pair<Declaration.Data, CgValue>>, namer: Namer): Pair<List<CgOp>,CgValue> {
    return when (this) {
        null ->
            throw IllegalStateException("Dangling null DataRef")

        is DataRef.Unresolved ->
            throw IllegalStateException("Dangling unresolved DataRef")

        is DataRef.Resolved -> {
            when (scope) {
                is Scope.Member ->
                    throw IllegalStateException("Dangling member scope")

                Scope.Local -> {
                    val (_, value) = locals[id]!!
                    Pair(listOf(), value)
                }

                Scope.Global ->
                    when (val data = globals.data[id]) {
                        null ->
                            throw IllegalStateException("Missing declaration for given DataRef")

                        is Declaration.Let -> {
                            val result = CgValue.Register(namer.toString(), type)
                            Pair(listOf(CgOp.Load(result, CgValue.Global(data.globalDataName(), CgTypePointer(type)))), result)
                        }

                        is Declaration.Function -> {
                            val result = CgValue.Register(namer.toString(), type)
                            Pair(listOf(CgOp.LoadStaticCallable(result, CgValue.UNIT, data.globalDataName())), result)
                        }
                    }
            }
        }
    }
}



private fun Declaration.Type.toCgType(globals: Globals) = when (this) {
    is Declaration.Alias  -> throw IllegalStateException("Dangling alias")
//    is Declaration.Struct -> toCgType(globals)
    is Declaration.Klass  -> CgTypePrimitive.OBJECT
}

private fun TypeRef.Tuple.toCgType(globals: Globals) =
    CgTypeStruct(fields.map { it.typeRef.toCgType(globals) })

private fun TypeRef.Primitive.toCgType() = when (kind) {
    PrimitiveKind.Bool    -> CgTypePrimitive.BOOL
    PrimitiveKind.Int8    -> CgTypePrimitive.INT8
    PrimitiveKind.Int16   -> CgTypePrimitive.INT16
    PrimitiveKind.Int32   -> CgTypePrimitive.INT32
    PrimitiveKind.Int64   -> CgTypePrimitive.INT64
    PrimitiveKind.Float32 -> CgTypePrimitive.FLOAT32
    PrimitiveKind.Float64 -> CgTypePrimitive.FLOAT64
}

private fun TypeRef?.toCgType(globals: Globals): CgType {
    return when (this) {
        null ->
            throw IllegalStateException("Danging null TypeRef")

        TypeRef.Unit ->
            CgTypePrimitive.OBJECT

        is TypeRef.Unresolved ->
            throw IllegalStateException("Dangling unresolved TypeRef")

        is TypeRef.Named ->
            (globals.type[id] ?: throw IllegalStateException("Type lookup failure")).toCgType(globals)

        is TypeRef.Callable ->
            CgTypeStruct.functionPointer

        is TypeRef.Tuple ->
            toCgType(globals)

        is TypeRef.Primitive ->
            toCgType()
    }
}



private fun CgValue.extractAll(namer: Namer): Pair<List<CgOp>, List<CgValue>> {
    return when (val type = type) {
        is CgTypeStruct -> {
            val ops = type.fields.mapIndexed { index, field ->
                CgOp.ExtractValue(namer.plus(index).toString(), this, intArrayOf(index))
            }
            val values = ops.map { it.result }
            Pair(ops, values)
        }
        else ->
            Pair(listOf(), listOf(this))
    }
}

private fun Declaration.Klass.findMember(id: Namer, globals: Globals): Declaration.Data? {
    return parameters.firstOrNull { it.id == id }
        ?: members.firstOrNull { it.id == id }
        ?: extends.firstNotNullOfOrNull {
            (globals.type[(it as TypeRef.Named).id] as Declaration.Klass).findMember(id, globals)
        }
}

private fun Expression.Let.toLetCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    val (valueOps, valueReg) = let.body!!.toCgOps(namer + 1, globals, locals)
    val (tailOps, tailReg) = tail.toCgOps(namer + 2, globals, locals + Pair(let.id, let to valueReg))
    return (valueOps + tailOps) to tailReg
}

private fun Expression.LoadMember.loadMemberToCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
    getIndex: (Declaration.Let, CgValue) -> Pair<List<CgOp>, CgValue?> = { _, _ -> Pair(listOf(), null) }
): Pair<List<CgOp>, CgValue> {
    val (baseOps, baseReg) = base.toCgOps(namer + 1, globals, locals)

    val result = when (val declaration = globals.type[(base.typeRef as TypeRef.Named).id]) {
        is Declaration.Klass -> {
            val member = declaration.findMember(id!!, globals)
                ?: throw IllegalStateException("Member $id of ${declaration.name} not found")

            if (member is Declaration.Let) {
                // Member variable
                val memberIndex = declaration.parameters.indexOfFirst { it.id == member.id }
                if (memberIndex < 0) throw IllegalStateException("Member $id of ${declaration.name} not found")

                val objectName = globalTypeName(declaration.name, declaration.id)
                val type = member.typeRef.toCgType(globals)

                val (indexOps, indexReg) = getIndex(member, baseReg)

                val gopReg = CgValue.Register(namer.plus(2).toString(), CgTypePointer(type))
                val gopOp = CgOp.GetObjectFieldPtr(gopReg, baseReg, objectName, memberIndex, indexReg)

                val loadReg = CgValue.Register(namer.plus(3).toString(), type)
                val loadOp = CgOp.Load(loadReg, gopReg)

                Pair(baseOps + indexOps + gopOp + loadOp, loadReg)

            } else if (declaration.isInterface) {
                // Virtual function call
                val loadOp = CgOp.LoadVirtualCallable(namer.plus(2).toString(), baseReg, member.signature!!)

                Pair(baseOps + loadOp, loadOp.result)

            } else {
                // Static function call
                member.body ?: throw IllegalStateException("Member $id of ${declaration.name} has no body")

                val funcName = member.globalDataName()
                val loadOp = CgOp.LoadStaticCallable(namer.plus(2).toString(), baseReg, funcName)

                Pair(baseOps + loadOp, loadOp.result)
            }
        }

        else -> TODO("LoadMember on type ${declaration?.javaClass?.name}")
    }

    return result
}


private fun Expression.Call.callToCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>
): Pair<List<CgOp>, CgValue> {
    // Try to emit relatively efficient code here in order to make the LLVM IR output more readable. It won't
    // affect the final optimised output from OPT, but does make debugging the compiler easier.

    val resultReg = CgValue.Register((namer + 2).toString(), typeRef.toCgType(globals))
    val params = parameter.fields.mapIndexed { index, param ->
        param.expression.toCgOps(namer + (3 + index), globals, locals)
    }
    val paramVals = params.map { (_, value) -> value }
    val paramOps = params.flatMap { (ops, _) -> ops }

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
            val declaration = globals.type[(callable.base.typeRef as TypeRef.Named).id]
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

private fun calculateDynamicArraySize(
    base: CgValue,
    klass: Declaration.Klass,
    member: Declaration.Let,
    namer: Namer,
    globals: Globals,
): Pair<List<CgOp>, CgValue> {
    val dataRefs = member.dynamicArraySize!!.findLocalDataReferences()

    val loadNamer = namer+1
    val (loaderOps, loaderValues) = klass.parameters.mapIndexed { index, param ->
        if (param.id in dataRefs) {
            // Expression does reference this klass parameter, so we need to load the field into
            // a register.
            val type = param.typeRef.toCgType(globals)
            val pointer = CgValue.Register(loadNamer.toString(index * 2 + 0), CgTypePointer(type))
            val value = CgValue.Register(loadNamer.toString(index * 2 + 1), type)
            listOf(
                CgOp.GetObjectFieldPtr(pointer, base, globalTypeName(klass.name, klass.id), index),
                CgOp.Load(value, pointer)
            ) to value
        } else {
            // Expression doesn't use this field. LLVM would optimize the load away, but I'd still prefer
            // to be able to visually parse the output, so we'll avoid emitting code in these cases.
            listOf<CgOp>() to CgValue.UNIT
        }
    }.invert()

    // Pass in fresh 'locals' lookup keyed by klass parameters, associated with CgValue generated up above
    // in 'paramRegs', and then generate IR from the expression. Result is ops and register.
    val newKlassLocals = klass.parameters.zip(loaderValues).dropLast(1).associate { (param, reg) ->
        param.id to Pair(param, reg)
    }

    val (arraySizeOps, arraySizeReg) = member.dynamicArraySize.toCgOps(namer+2, globals, newKlassLocals)

    return Pair(loaderOps.flatten() + arraySizeOps, arraySizeReg)
}

private fun Expression.ArrayLookup.toArrayLookupCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    return (array as Expression.LoadMember).loadMemberToCgOps(namer+2, globals, locals) { member, base ->
        val klass = globals.type[(array.base.typeRef as TypeRef.Named).id] as Declaration.Klass

        val (arraySizeOps, arraySizeReg) = if (member.dynamicArraySize != null) {
            calculateDynamicArraySize(base, klass, member, namer+3, globals)
        } else {
            Pair(listOf<CgOp>(), CgValue.Immediate(member.arraySize.toString(), CgTypePrimitive.INT32))
        }

        val (indexOps, indexReg) = index.toCgOps(namer+1, globals, locals)

        val checkOp = CgOp.CheckArrayAccess(indexReg, arraySizeReg)

        Pair(arraySizeOps + indexOps + checkOp, indexReg)
    }
}


private fun Expression.NewKlass.toNewKlassCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    val type = typeRef as TypeRef.Named
    val typeName = globalTypeName(type.name, type.id)
    val klass = globals.type[type.id] as Declaration.Klass
    val fieldNamer = namer + 9

    val (paramOpsTmp, paramRegs) = parameter.fields.mapIndexed { fieldIndex, tupleField ->
        tupleField.expression.toCgOps(fieldNamer + fieldIndex, globals, locals)
    }.invert()
    val paramOps = paramOpsTmp.flatten()

    val newReg = CgValue.Register(namer.toString(1), CgTypePrimitive.OBJECT)
    val lastParam = klass.parameters.lastOrNull()
    val dynamicArraySize = lastParam?.dynamicArraySize
    val arraySize = lastParam?.arraySize

    val (newOps, arraySizeReg) = if (dynamicArraySize != null) {
        // Pass in fresh 'locals' lookup keyed by klass parameters, associated with CgValue generated up above
        // in 'paramRegs', and then generate IR from the expression. Result is ops and register.
        val newKlassLocals = klass.parameters.zip(paramRegs).dropLast(1).associate { (param, reg) ->
            param.id to Pair(param, reg)
        }
        val (arraySizeOps, arraySizeReg) = dynamicArraySize.toCgOps(namer + 3, globals, newKlassLocals)
        
        Pair(arraySizeOps + CgOp.NewArray(
            newReg, typeName,
            klass.parameters.last().typeRef.toCgType(globals),
            klass.parameters.size - 1,
            arraySizeReg)
        , arraySizeReg)

        /*
        // Array container. A bit of a hack, by creating a dummy object on the stack with minimal size
        // we can initialise the members (except the array) and then call the sizing function. LLVM
        // should be able to optimize this away, and it saves us from duplicating the sizing expression.

        val dummyReg = CgValue.Register(namer.toString(2), CgTypePrimitive.OBJECT)
        val sizeCheckReg = CgValue.Register(namer.toString(4), CgTypePrimitive.BOOL)
        val sizingFunction = klass.members.single { it.name == "array\$size" }.globalDataName()
        listOf(
            // Use sizing function with dummy object, last arg is array, don't use it
            CgOp.DummyObjectOnStack(dummyReg, typeName, paramRegs.dropLast(1)),
            CgOp.CallStatic(arraySizeReg, dummyReg, sizingFunction, listOf()),

            // Must not be bigger than maximum allowable array size
            CgOp.BinaryMath(
                sizeCheckReg,
                "icmp ule",
                arraySizeReg,
                CgValue.Immediate(arraySize.toString(), CgTypePrimitive.INT32)
            ),
            CgOp.Assert(sizeCheckReg, "array allocation exceeds upper bound"),

            CgOp.NewArray(
                newReg,
                typeName,
                klass.parameters.last().typeRef.toCgType(globals),
                klass.parameters.size - 1,
                arraySizeReg
            )
        )
        */

    } else if (arraySize != null) {
        // Array container of fixed size
        val arraySizeReg = CgValue.Immediate(arraySize.toString(), CgTypePrimitive.INT32)
        Pair(listOf(CgOp.NewArray(
            newReg, typeName,
            klass.parameters.last().typeRef.toCgType(globals),
            klass.parameters.size - 1,
            arraySizeReg)
        ), arraySizeReg)

    } else {
        // Normal object
        Pair(listOf(
            CgOp.New(newReg, typeName)
        ), CgValue.ZERO)
    }

    val initOps = paramRegs.zip(klass.parameters).flatMapIndexed { fieldIndex, (paramReg, parameterDefinition) ->
        val fieldNamer = fieldNamer + fieldIndex

        if (parameterDefinition.arraySize != null) {
            // Array field, value is a lambda to initialise elements
            val headLabel = CgOp.Label(fieldNamer.toString(1))
            val bodyLabel = CgOp.Label(fieldNamer.toString(2))
            val exitLabel = CgOp.Label(fieldNamer.toString(3))
            val testLabel = CgOp.Label(fieldNamer.toString(4))

            val indexReg = CgValue.Register(fieldNamer.toString(5), CgTypePrimitive.INT32)
            val valueReg = CgValue.Register(fieldNamer.toString(6), parameterDefinition.typeRef.toCgType(globals))
            val indexTmpReg = CgValue.Register(fieldNamer.toString(7), CgTypePrimitive.INT32)
            val compareReg = CgValue.Register(fieldNamer.toString(8), CgTypePrimitive.BOOL)
            val fieldPtrReg = CgValue.Register(fieldNamer.toString(9), CgTypePointer(valueReg.type))

            listOf(
                CgOp.Jump(headLabel.name),
                headLabel,
                CgOp.Jump(testLabel.name),

                testLabel,
                CgOp.Phi(indexReg, listOf(CgValue.ZERO to headLabel.name, indexTmpReg to bodyLabel.name)),
                CgOp.BinaryMath(compareReg, "icmp ult", indexReg, arraySizeReg),
                CgOp.Branch(compareReg, bodyLabel.name, exitLabel.name),

                bodyLabel,
                CgOp.Call(valueReg, paramReg, listOf(indexReg)),
                CgOp.GetObjectFieldPtr(fieldPtrReg, newReg, typeName, fieldIndex, indexReg),
                CgOp.Store(valueReg.type, fieldPtrReg, valueReg),
                CgOp.BinaryMath(indexTmpReg, "add", indexReg, CgValue.ONE),
                CgOp.Jump(testLabel.name),

                exitLabel,
            )
        } else {
            // Normal field
            val fieldPtrReg = CgValue.Register(fieldNamer.toString(2), CgTypePointer(paramReg.type))
            val getFieldOp = CgOp.GetObjectFieldPtr(fieldPtrReg, newReg, typeName, fieldIndex)
            val writeOp = CgOp.Store(paramReg.type, fieldPtrReg, paramReg)
            listOf(getFieldOp, writeOp)
        }
    }

    return Pair(paramOps + newOps + initOps, newReg)
}


private fun Expression.tupleOrArrayToCgOps(
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

private fun Expression.toCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>
): Pair<List<CgOp>, CgValue> {
    return when (this) {
        is Expression.Characters -> TODO()
        is Expression.Float -> TODO()

        is Expression.Let ->
            toLetCgOps(namer, globals, locals)

        is Expression.Assert ->
            toAssertCgOps(namer, globals, locals)

        is Expression.ArrayLookup ->
            toArrayLookupCgOps(namer, globals, locals)

        is Expression.Tuple ->
            tupleOrArrayToCgOps(namer, globals, locals, fields.map { it.expression })

        is Expression.Lambda ->
            throw IllegalStateException("No lambda should exist here")

        is Expression.Integer -> {
            val type = typeRef.toCgType(globals)
            Pair(listOf(), CgValue.Immediate(value.toString(), type))
        }

        is Expression.NewKlass ->
            toNewKlassCgOps(namer, globals, locals)

        is Expression.LoadMember ->
            loadMemberToCgOps(namer, globals, locals)

        is Expression.Call ->
            callToCgOps(namer, globals, locals)

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

private fun Declaration.Function.toIntermediateExternalFunction(
    namer: Namer,
    globals: Globals
): List<CgThingExternalFunction> {
    val params = (listOf(thisDeclaration) + parameters).map { param ->
        val paramType = param.typeRef.toCgType(globals)
        CgValue.Register(localName(param.name, param.id), paramType)
    }

    return listOf(CgThingExternalFunction(
        globalDataName(),
        name.substringAfterLast("::"),
        typeRef.result!!.toCgType(globals),
        params,
    ))
}

private fun Declaration.Function.toIntermediateFunction(
    namer: Namer,
    globals: Globals
): List<CgThingFunction> {
    val body = body!!
    val type = typeRef

    val locals = (listOf(thisDeclaration) + parameters).associate {
        it.id to Pair(it, CgValue.Register(localName(it.name, it.id), it.typeRef!!.toCgType(globals)))
    }

    val (ops, returnValue) = body.toCgOps(namer, globals, locals)

    return listOf(CgThingFunction(
        globalDataName(),
        signature!!,
        type.result!!.toCgType(globals),
        locals.values.map { (_, value) -> value },
        listOf(),
        ops + CgOp.Return(returnValue)
    ))
}

private fun Declaration.Klass.justGetTheMembers(namer: Namer, globals: Globals): List<CgThing> {
    // Emit default implementations.. Remember all 'this.' must use virtual calls.
    return members.flatMapIndexed { index, function ->
        if (function.body == null) listOf()
        else function.toIntermediateFunction(namer + index, globals)
    }
}

private fun Declaration.Klass.findVTableEntries(globals: Globals): Map<String, String> {
    val ourMembers = members
        .filter { it.body != null }
        .associate { it.signature!! to it.globalDataName() }
    val allMembers = extends.fold(ourMembers) { acc, typeRef ->
        acc + (globals.type[(typeRef as TypeRef.Named).id] as Declaration.Klass).findVTableEntries(globals)
    }
    return allMembers
}

private fun Declaration.Klass.toIntermediateKlass(namer: Namer, globals: Globals): List<CgThing> {
    // Emit class definition with vtable, member implementations and deleter

    val className = globalTypeName(name, id)

//    val cleanUpId = namer + 1
//    val cleanupCode = parameters.flatMapIndexed { index, param ->
//        if (param.typeRef.toCgType(globals) == CgTypePrimitive.OBJECT) {
//            val regName = cleanUpId.toString(index)
//            // TODO: Handle nested structure fields as well
//            val ptrReg = CgValue.Register("$regName.p", CgTypePointer(CgTypePrimitive.OBJECT))
//            listOf(
//                CgOp.GetObjectFieldPtr(ptrReg, CgValue.THIS, className, index),
//                CgOp.Release(ptrReg)
//            )
//        } else {
//            listOf()
//        }
//    }

    val arrayParam = parameters.lastOrNull()?.takeIf { it.arraySize != null }
    val fields = parameters.map { CgClassField(it.typeRef.toCgType(globals), it.arraySize != null) }
    val deleteOps = if (arrayParam != null) {
        val (sizeOps, sizeReg) = if (arrayParam.dynamicArraySize != null) {
            calculateDynamicArraySize(CgValue.THIS, this, arrayParam, namer, globals)
        } else {
            Pair(listOf<CgOp>(), CgValue.Immediate(arrayParam.arraySize.toString(), CgTypePrimitive.INT32))
        }
        sizeOps +
            CgOp.DeleteArray(CgValue.THIS, className, sizeReg) +
            CgOp.Return(CgValue.VOID)
    } else {
        listOf(
            CgOp.Delete(CgValue.THIS, className),
            CgOp.Return(CgValue.VOID)
        )
    }

    val deleter = CgThingFunction(
        "delete\$$className",
        "delete",
        CgTypePrimitive.VOID,
        listOf(CgValue.THIS),
        listOf(),
        deleteOps
    )

    val vtable = findVTableEntries(globals)

    return justGetTheMembers(namer + 2, globals) + listOf<CgThing>(deleter) +
            CgThingClass(className, fields, vtable, deleter.globalName)
}

private fun Declaration.Let.toIntermediateVariable(namer: Namer, globals: Globals): List<CgThing> {
    val body = body!!
    val globalName = globalDataName()
    val type = typeRef.toCgType(globals)

    if (body is Expression.Characters) {
        // Static string

        val stringClass = globals.type.values.first { it is Declaration.Klass && it.name == "System::String" }
        val stringBytes = body.value.encodeToByteArray()

        return listOf(
            CgThingClassInstance(
                globalName,
                globalTypeName(stringClass.name, stringClass.id),
                listOf(stringBytes.size, stringBytes)
            )
        )

    } else {
        // Variable and init function
        val (ops, result) = body.toCgOps(namer, globals, mapOf())

        return listOf(
            CgThingVariable(globalName, type),
            CgThingFunction(
                "init\$$globalName",
                "init",
                type,
                listOf(CgValue.THIS),
                listOf(),
                ops + CgOp.Return(result)
            )
        )
    }
}

/* There should be no nested lambdas remaining, so all variable references are either
 * global, parameter or immediate local, with no nested functions.
 */
fun convertToIntermediate(ast: Ast): List<CgThing> {
    val globals = Globals(
        ast.declarations.mapNotNull { it.declaration as? Declaration.Type }.associateBy { it.id },
        ast.declarations.mapNotNull { it.declaration as? Declaration.Data }.associateBy { it.id })

    val namer = Namer("r")
    val things = ast.declarations.flatMapIndexed { index, (imports, declaration) ->
        val namer = namer + index

        when (declaration) {
            is Declaration.Klass ->
                if (declaration.isInterface)
                    declaration.justGetTheMembers(namer, globals)
                else
                    declaration.toIntermediateKlass(namer, globals)

            is Declaration.Alias ->
                listOf()

            is Declaration.Let ->
                declaration.toIntermediateVariable(namer, globals)

            is Declaration.Function ->
                if ("extern" in declaration.attributes)
                     declaration.toIntermediateExternalFunction(namer, globals)
                else declaration.toIntermediateFunction(namer, globals)
        }
    }

    val functions = things.filterIsInstance<CgThingFunction>().associateBy { it.globalName }
    val variables = things.filterIsInstance<CgThingVariable>().associateBy { it.name }

    // Create main function and append it
    val userMainList = globals.data.values
        .filterIsInstance<Declaration.Function>()
        .filter {
            (it.name == "main" || it.name.endsWith("::main")) && it.parameters.isEmpty() && it.body?.typeRef == TypeRef.Primitive(
                PrimitiveKind.Int32
            )
        }
    val userMain = userMainList.firstOrNull()

    if (userMain == null) {
        throw IllegalStateException("No main function found")
    } else if (userMainList.size > 1) {
        throw IllegalStateException("Too many user main functions found")
    }

    val globalVars = functions.filterKeys { it.startsWith("init\$") }.map { (_, initFunc) ->
        Pair(variables[initFunc.globalName.drop(5)]!!, initFunc)
    }

    val initNamer = Namer("i")
    val initOps = globalVars.flatMapIndexed { index, (thing, initFunc) ->
        val namerBase = initNamer + index

        val methodReg = CgValue.Register(namerBase.plus(0).toString(), CgTypeStruct.functionPointer)
        val resultReg = CgValue.Register(namerBase.plus(1).toString(), thing.type)
        listOf(
            CgOp.CallStatic(resultReg, CgValue.UNIT, initFunc.globalName, listOf()),
            CgOp.Store(thing.type, CgValue.Global(thing.name, thing.type), resultReg)
        )
    }

    val mainNamer = initNamer + globalVars.size
    val mainMethodReg = CgValue.Register(mainNamer.plus(0).toString(), CgTypeStruct.functionPointer)
    val mainResultReg = CgValue.Register(mainNamer.plus(1).toString(), CgTypePrimitive.INT32)
    val retOps = listOf(
        CgOp.CallStatic(mainResultReg, CgValue.UNIT, userMain.globalDataName(), listOf()),
        CgOp.Return(mainResultReg)
    )

    val main = CgThingFunction(
        "synth_main",
        "",
        CgTypePrimitive.INT32,
        listOf(CgValue.THIS),
        listOf(),
        initOps + retOps
    )

    // Return everything and the synthetic main function
    return things + (main as CgThing)
}