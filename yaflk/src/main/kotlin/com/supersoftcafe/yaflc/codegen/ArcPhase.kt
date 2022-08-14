package com.supersoftcafe.yaflc.codegen

private fun FindObjectFields(type: CgType): List<IntArray> {
    return when (type) {
        CgTypePrimitive.OBJECT -> listOf(intArrayOf())
        is CgTypeStruct -> type.fields.flatMapIndexed { index, fieldType ->
            FindObjectFields(fieldType).map { intArrayOf(index) + it }
        }
        else -> listOf()
    }
}

fun ArcPhase(thing: CgThingFunction): CgThingFunction {
    // Declarations of ARC variables that hold references for later release
    val arcVars = thing.body.flatMap { op ->
        val objectFields = FindObjectFields(op.resultType)
        if (objectFields.isNotEmpty() && (op is CgOp.New || op is CgOp.Call)) {
            objectFields.map { fieldPath ->
                val pathStr = fieldPath.joinToString("$")
                CgThingVariable("${op.result}.arc$pathStr", CgTypePrimitive.OBJECT)
            }
        } else {
            listOf()
        }
    }

    // Insert ARC code after New/Call and before Ret
    val modifiedBody = thing.body.flatMapIndexed { opIndex, op ->
        val objectFields = FindObjectFields(op.resultType)
        if (objectFields.isNotEmpty() && (op is CgOp.New || op is CgOp.Call)) {
            // Store value(s) for a later release just before the return statement
            listOf(op) + objectFields.flatMap { fieldPath ->
                val pathStr = fieldPath.joinToString("$")
                val from = op.result + pathStr
                val store = CgOp.Store(CgTypePrimitive.OBJECT, "${op.result}.arc$pathStr", from)
                if (fieldPath.isNotEmpty()) {
                    listOf(CgOp.ExtractValue(from, op.result, op.resultType, fieldPath), store)
                } else {
                    listOf(store)
                }
            }

        } else if (op is CgOp.Return) {
            // Acquire the return, but then release everything. Return is safe due to extra acquire.
            val releases = arcVars.map { arcVar -> CgOp.Release(arcVar.name) }
            if (op.resultType == CgTypePrimitive.OBJECT)
                 listOf(CgOp.Acquire(op.returnReg)) + releases + op
            else releases + op

        } else {
            listOf(op)
        }
    }

    // Insert the initialisation of ARC variables as the first operation of the function
    val zeroInits = arcVars.map { arcVar ->
        CgOp.Store(CgTypePrimitive.OBJECT, arcVar.name, "null")
    }

    return thing
        .copy(body = modifiedBody)
        .addPreamble(zeroInits)
        .copy(variables = thing.variables + arcVars)
}

