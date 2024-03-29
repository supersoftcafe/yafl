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

fun arcPhase(thing: CgThingFunction): CgThingFunction {
    // Declarations of ARC variables that hold references for later release
    val arcVars = thing.body.flatMap { op ->
        val objectFields = findObjectFields(op.result.type)
        if (objectFields.isNotEmpty() && (op is CgOp.New || op is CgOp.Call)) {
            objectFields.map { fieldPath ->
                val pathStr = fieldPath.joinToString("$")
                CgThingVariable("${op.result.name}.arc$pathStr", CgTypePrimitive.OBJECT)
            }
        } else {
            listOf()
        }
    }

    // Insert ARC code after New/Call and before Ret
    val modifiedBody = thing.body.flatMapIndexed { opIndex, op ->
        when (op) {
            is CgOp.New, is CgOp.Call -> {
                val objectFields = findObjectFields(op.result.type)
                if (objectFields.isNotEmpty()) {
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

                // Acquire the return, but then release everything. Return is safe due to extra acquire.
                val acquires = objectFields.flatMap { fieldPath ->
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

                val releases = arcVars.map { arcVar ->
                    CgOp.Release(CgValue.Register(arcVar.name, CgTypePointer(CgTypePrimitive.OBJECT)))
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
        CgOp.Store(CgTypePrimitive.OBJECT, CgValue.Register(arcVar.name, CgTypePointer(CgTypePrimitive.OBJECT)), CgValue.NULL)
    }

    return thing
        .copy(body = modifiedBody)
        .addPreamble(zeroInits)
        .copy(variables = thing.variables + arcVars)
}

