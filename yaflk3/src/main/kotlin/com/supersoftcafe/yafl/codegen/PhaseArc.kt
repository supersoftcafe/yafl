package com.supersoftcafe.yafl.codegen

private fun findObjectFields(type: CgType): List<IntArray> {
    return when (type) {
        CgTypePrimitive.OBJECT -> listOf(intArrayOf())
        is CgTypeStruct -> type.fields.flatMapIndexed { index, fieldType ->
            findObjectFields(fieldType).map { intArrayOf(index) + it }
        }
        else -> listOf()
    }
}

fun phaseArc(thing: CgThing): List<CgThing> {
    if (thing !is CgThingFunction)
        return listOf(thing)

    // If there is a single return statement we can exclude the register it
    // references from ARC processing, IIF that register is set from a single
    // call to New/NewArray or Call. Quite specific, but also quite common.
    val registerToExclude = (thing.body.singleOrNull { it is CgOp.Return } as? CgOp.Return) ?.returnValue ?. let { reg ->
        thing.body.singleOrNull {
            (it is CgOp.New || it is CgOp.NewArray || it is CgOp.Call) &&
                    it.result == reg
        }?.result }

    // Find all registers that are the result of a call to New or NewArray
    val registerOfNew = thing.body.mapNotNull {
        if (it is CgOp.New)
            it.result
        else if (it is CgOp.NewArray)
            it.result
        else
            null
    }.toSet()

    // Using results of New/NewArray find all GEPs that derive a member pointer from them
    // This will be used to identify Store operations that need a call to acquire
    val registerOfGep = thing.body.mapNotNull {
        if (it is CgOp.GetObjectFieldPtr && it.pointer in registerOfNew)
            it.result
        else
            null
    }.toSet()

    // Declarations of ARC variables that hold references for later release
    val arcVars = thing.body.flatMap { op ->
        val objectFields = findObjectFields(op.result.type)
        if (op.result != registerToExclude && objectFields.isNotEmpty() && (op is CgOp.New || op is CgOp.NewArray|| op is CgOp.Call || op is CgOp.CallStatic || op is CgOp.CallVirtual)) {
            objectFields.map { fieldPath ->
                val pathStr = fieldPath.joinToString("$")
                CgOp.Alloca("${op.result.name}.arc$pathStr", CgTypePrimitive.OBJECT)
            }
        } else {
            listOf()
        }
    }

    // Insert ARC code after New/Call and before Ret
    val modifiedBody = thing.body.flatMapIndexed { opIndex, op ->
        when (op) {
            is CgOp.Store -> {
                val objectFields = findObjectFields(op.value.type)
                if (op.pointer in registerOfGep && objectFields.isNotEmpty()) {
                    // If this is a store to initialise an object field, we might need to call acquire
                    val reg = op.value as CgValue.Register
                    listOf(op) + objectFields.flatMap { fieldPath ->
                        val pathStr = fieldPath.joinToString("$")
                        if (fieldPath.isNotEmpty()) {
                            val from = CgValue.Register(reg.name + pathStr, CgTypePrimitive.OBJECT)
                            val extract = CgOp.ExtractValue(from, reg, fieldPath)
                            val acquire = CgOp.Acquire(from)
                            listOf(extract, acquire)
                        } else {
                            listOf(CgOp.Acquire(op.value))
                        }
                    }
                } else {
                    listOf(op)
                }
            }

            is CgOp.New, is CgOp.NewArray, is CgOp.Call, is CgOp.CallStatic, is CgOp.CallVirtual -> {
                val objectFields = findObjectFields(op.result.type)
                if (op.result != registerToExclude && objectFields.isNotEmpty()) {
                    // Store value(s) for a later release just before the return statement
                    listOf(op) + objectFields.flatMap { fieldPath ->
                        val pathStr = fieldPath.joinToString("$")
                        if (fieldPath.isNotEmpty()) {
                            val from = CgValue.Register(op.result.name + pathStr, CgTypePrimitive.OBJECT)
                            val extract = CgOp.ExtractValue(from, op.result, fieldPath)
                            val store = CgOp.Store(CgTypePrimitive.OBJECT, CgValue.Register("${op.result.name}.arc$pathStr", CgTypePointer(from.type)), from)
                            listOf(extract, store)
                        } else {
                            val store = CgOp.Store(CgTypePrimitive.OBJECT, CgValue.Register("${op.result.name}.arc", CgTypePointer(op.result.type)), op.result)
                            listOf(store)
                        }
                    }
                } else {
                    listOf(op)
                }
            }

            is CgOp.Return -> {
                val objectFields = findObjectFields(op.returnValue.type)

                val acquires = if (op.returnValue != registerToExclude && objectFields.isNotEmpty()) {
                    // Acquire the return, but then release everything. Return is safe due to extra acquire.
                    objectFields.flatMap { fieldPath ->
                        val pathStr = fieldPath.joinToString("$")
                        if (fieldPath.isNotEmpty()) {
                            val from = CgValue.Register((op.returnValue as CgValue.Register).name + pathStr, CgTypePrimitive.OBJECT)
                            val extract = CgOp.ExtractValue(from, op.returnValue, fieldPath)
                            val acquire = CgOp.Acquire(from)
                            listOf(extract, acquire)
                        } else {
                            listOf(CgOp.Acquire(op.returnValue))
                        }
                    }
                } else {
                    listOf()
                }

                val releases = arcVars.map { arcVar ->
                    CgOp.Release(arcVar.result)
                }

                acquires + releases + op
            }

            else -> {
                listOf(op)
            }
        }
    }

    // Insert the initialisation of ARC variables as the first operation of the function
    val zeroInits = arcVars.map { arcVar ->
        CgOp.Store(CgTypePrimitive.OBJECT, arcVar.result, CgValue.NULL)
    }

    return listOf(thing
        .copy(body = arcVars + modifiedBody)
        .addPreamble(zeroInits))
}

