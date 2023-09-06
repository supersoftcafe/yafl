package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.Expression
import com.supersoftcafe.yafl.models.ast.TypeRef
import com.supersoftcafe.yafl.models.llir.*
import com.supersoftcafe.yafl.passes.p5_generate.*
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.mapFirst
import com.supersoftcafe.yafl.utils.splitIntoTwoLists



fun Expression.LoadMember.loadMemberToCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
    getIndex: (Declaration.Let, CgValue) -> Pair<List<CgOp>, CgValue?> = { _, _ -> Pair(listOf(), null) }
): Pair<List<CgOp>, CgValue> {
    val (baseOps, baseReg) = base.toCgOps(namer + 1, globals, locals)

    val result = when (val declaration = globals.type[(base.typeRef as TypeRef.Klass).id]) {
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

fun Expression.ArrayLookup.toArrayLookupCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    return (array as Expression.LoadMember).loadMemberToCgOps(namer+2, globals, locals) { member, base ->
        val klass = globals.type[(array.base.typeRef as TypeRef.Klass).id] as Declaration.Klass

        val (arraySizeOps, arraySizeReg) =
            if (member.dynamicArraySize == null)
                 Pair(listOf<CgOp>(), CgValue.Immediate(member.arraySize.toString(), CgTypePrimitive.INT32))
            else calculateDynamicArraySize(base, klass, member, namer+3, globals)

        val (indexOps, indexReg) = index.toCgOps(namer+1, globals, locals)
        val checkOp = CgOp.CheckArrayAccess(indexReg, arraySizeReg)
        Pair(arraySizeOps + indexOps + checkOp, indexReg)
    }
}


fun Expression.NewKlass.toNewKlassCgOps(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    val type = typeRef as TypeRef.Klass
    val typeName = globalTypeName(type.name, type.id)
    val klass = globals.type[type.id] as Declaration.Klass
    val fieldNamer = namer + 9

    val (paramOps, paramRegs) = parameter.evaluateAndExtractTupleFields(fieldNamer, globals, locals)

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
                arraySizeReg),
            arraySizeReg)

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
        Pair(
            listOf(
                CgOp.NewArray(
                    newReg, typeName,
                    klass.parameters.last().typeRef.toCgType(globals),
                    klass.parameters.size - 1,
                    arraySizeReg)
            ), arraySizeReg)

    } else {
        // Normal object
        Pair(
            listOf(
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




private fun Declaration.Klass.findVTableEntries(globals: Globals): Map<String, String> {
    val ourMembers = members
        .filter { it.body != null }
        .associate { it.signature!! to it.globalDataName() }
    val allMembers = extends.fold(ourMembers) { acc, typeRef ->
        acc + (globals.type[(typeRef as TypeRef.Klass).id] as Declaration.Klass).findVTableEntries(globals)
    }
    return allMembers
}

private fun Declaration.Klass.justGetTheMembers(namer: Namer, globals: Globals): List<CgThing> {
    // Emit default implementations.. Remember all 'this.' must use virtual calls.
    return members.flatMapIndexed { index, function ->
        if (function.body == null)
             listOf()
        else function.functionToIntermediate(namer + index, globals)
    }
}

private fun Declaration.Klass.getTheVtableAndMembers(namer: Namer, globals: Globals): List<CgThing> {
    // Emit class definition with vtable, member implementations and destructor

    val className = globalTypeName(name, id)

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
        deleteOps
    )

    val vtable = findVTableEntries(globals)

    return justGetTheMembers(namer + 2, globals) + listOf<CgThing>(deleter) +
            CgThingClass(className, fields, vtable, deleter.globalName)
}

fun Declaration.Klass.klassToIntermediate(namer: Namer, globals: Globals): List<CgThing> {
    return if (isInterface)
         justGetTheMembers(namer, globals)
    else getTheVtableAndMembers(namer, globals)
}

