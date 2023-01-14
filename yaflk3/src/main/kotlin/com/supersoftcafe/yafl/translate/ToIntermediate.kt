package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.codegen.*
import com.supersoftcafe.yafl.utils.*



private class Globals(val type: Map<Namer, Declaration.Type>, val data: Map<Namer, Declaration.Data>)

private fun localName(name: String, id: Namer) = "l$$name$$id"
private fun Declaration.Data.globalDataName() = "d$$signature$$id"
private fun globalTypeName(name: String, id: Namer) = "t$$name$$id"


private fun DataRef?.toCgValue(type: CgType, globals: Globals, namer: Namer): Pair<List<CgOp>,CgValue> {
    return when (this) {
        null ->
            throw IllegalStateException("Dangling null DataRef")

        is DataRef.Unresolved ->
            throw IllegalStateException("Dangling unresolved DataRef")

        is DataRef.Resolved -> {
            when (scope) {
                is Scope.Member ->
                    throw IllegalStateException("Dangling member scope")

                Scope.Local ->
                    Pair(listOf(), CgValue.Register(localName(name, id), type))

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

private fun Expression.LoadMember.loadMemberToCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Declaration.Data>,
    getIndex: (Declaration.Let) -> Pair<List<CgOp>, CgValue?> = { Pair(listOf(), null) }
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

                val (indexOps, indexReg) = getIndex(member)

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
    locals: Map<Namer, Declaration.Data>
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

private fun Expression.NewKlass.toNewKlassCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Declaration.Data>,
): Pair<List<CgOp>, CgValue> {
    val type = typeRef as TypeRef.Named
    val typeName = globalTypeName(type.name, type.id)
    val klass = globals.type[type.id] as Declaration.Klass

    val newReg = CgValue.Register(namer.toString(1), CgTypePrimitive.OBJECT)
    val newOp = CgOp.New(newReg, typeName)

    val initOps = parameter.fields.zip(klass.parameters).flatMapIndexed { fieldIndex, (tupleField, parameterDefinition) ->
        val namer = namer + (1 + fieldIndex)

        val arraySize = parameterDefinition.arraySize
        val (paramOps, paramReg) = tupleField.expression.toCgOps(namer + 1, globals, locals)

        if (arraySize != null) {
            // Array field, value is a lambda to initialise elements
            val sizeImm = CgValue.Immediate(arraySize.toString(), CgTypePrimitive.INT32)
            val headLabel = CgOp.Label(namer.toString(2))
            val bodyLabel = CgOp.Label(namer.toString(3))
            val exitLabel = CgOp.Label(namer.toString(4))
            val indexReg = CgValue.Register(namer.toString(5), CgTypePrimitive.INT32)
            val valueReg = CgValue.Register(namer.toString(6), parameterDefinition.typeRef.toCgType(globals))
            val indexTmpReg = CgValue.Register(namer.toString(7), CgTypePrimitive.INT32)
            val compareReg = CgValue.Register(namer.toString(8), CgTypePrimitive.BOOL)
            val fieldPtrReg = CgValue.Register(namer.toString(9), CgTypePointer(valueReg.type))

            paramOps + listOf(
                CgOp.Jump(headLabel.name),
                headLabel,
                CgOp.Jump(bodyLabel.name),
                bodyLabel,
                CgOp.Phi(indexReg, listOf(CgValue.ZERO to headLabel.name, indexTmpReg to bodyLabel.name)),
                CgOp.Call(valueReg, paramReg, listOf(indexReg)),
                CgOp.GetObjectFieldPtr(fieldPtrReg, newReg, typeName, fieldIndex, indexReg),
                CgOp.Store(valueReg.type, fieldPtrReg, valueReg),
                CgOp.BinaryMath(indexTmpReg, "add", indexReg, CgValue.ONE),
                CgOp.BinaryMath(compareReg, "icmp ult", indexTmpReg, sizeImm),
                CgOp.Branch(compareReg, bodyLabel.name, exitLabel.name),
                exitLabel,
            )
        } else {
            // Normal field
            val fieldPtrReg = CgValue.Register(namer.toString(2), CgTypePointer(paramReg.type))
            val getFieldOp = CgOp.GetObjectFieldPtr(fieldPtrReg, newReg, typeName, fieldIndex)
            val writeOp = CgOp.Store(paramReg.type, fieldPtrReg, paramReg)
            paramOps + getFieldOp + writeOp
        }
    }

    return Pair(listOf(newOp) + initOps, newReg)
}


private fun Expression.tupleOrArrayToCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Declaration.Data>,
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

private fun Expression.toCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Declaration.Data>
): Pair<List<CgOp>, CgValue> {
    return when (this) {
        is Expression.Characters -> TODO()
        is Expression.Float -> TODO()

        is Expression.ArrayLookup ->
            (array as Expression.LoadMember).loadMemberToCgOps(namer+2, globals, locals) { member ->
                val (indexOps, indexReg) = index.toCgOps(namer + 1, globals, locals)
                val check = CgOp.CheckArrayAccess(indexReg, member.arraySize!!.toInt())
                Pair(indexOps + check, indexReg)
            }

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
            dataRef.toCgValue(type, globals, namer)
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

    val (ops, returnValue) = body.toCgOps(
        namer, globals,
        parameters.associateBy { it.id })

    val params = (listOf(thisDeclaration) + parameters).map { param ->
        val paramType = param.typeRef.toCgType(globals)
        CgValue.Register(localName(param.name, param.id), paramType)
    }

    return listOf(CgThingFunction(
        globalDataName(),
        signature!!,
        type.result!!.toCgType(globals),
        params,
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

    val cleanupCode = parameters.flatMapIndexed { index, param ->
        if (param.typeRef.toCgType(globals) == CgTypePrimitive.OBJECT) {
            val regName = (namer + 1).toString()
            val ptrReg = CgValue.Register("$regName.p", CgTypePointer(CgTypePrimitive.OBJECT))
            val objReg = CgValue.Register("$regName.o", CgTypePrimitive.OBJECT)
            listOf(
                CgOp.GetObjectFieldPtr(ptrReg, CgValue.THIS, className, index),
                CgOp.Load(objReg, ptrReg),
                CgOp.Release(objReg)
            )
        } else {
            listOf()
        }
    }

    val deleter = CgThingFunction(
        "delete\$$className",
        "delete",
        CgTypePrimitive.VOID,
        listOf(CgValue.THIS),
        listOf(),
            cleanupCode.dropLast(1) +
            CgOp.Delete(CgValue.THIS, className) + // Insert delete just before final call to release, if exists
            cleanupCode.takeLast(1) + // Final release after delete, so it can tail call to avoid some stack overflows
            CgOp.Return(CgValue.VOID)
    )

    val fields = parameters.map { CgClassField(it.typeRef.toCgType(globals), it.arraySize?.toInt()) }
    val vtable = findVTableEntries(globals)

    return justGetTheMembers(namer, globals) +
            listOf<CgThing>(deleter) +
            CgThingClass(className, fields, vtable, deleter.globalName)
}

private fun Declaration.Let.toIntermediateVariable(namer: Namer, globals: Globals): List<CgThing> {
    val body = body!!

    // Variable and init function
    val type = typeRef.toCgType(globals)
    val (ops, result) = body.toCgOps(namer, globals, mapOf())

    val globalName = globalDataName()

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

/* There should be no nested lambdas remaining, so all variable references are either
 * global, parameter or immediate local, with no nested functions.
 */
fun convertToIntermediate(ast: Ast): List<CgThing> {
    // TODO: Locate the 'main' function. There must be only one, with no params and a single Int32 result.
    //    In below mapping, give that main function a well defined name

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