package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.llir.CgOp
import com.supersoftcafe.yafl.models.llir.CgTypePointer
import com.supersoftcafe.yafl.models.llir.CgValue
import com.supersoftcafe.yafl.passes.findLocalDataReferences
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.splitIntoTwoLists


fun calculateDynamicArraySize(
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
    }.splitIntoTwoLists()

    // Pass in fresh 'locals' lookup keyed by klass parameters, associated with CgValue generated up above
    // in 'paramRegs', and then generate IR from the expression. Result is ops and register.
    val newKlassLocals = klass.parameters.zip(loaderValues).dropLast(1).associate { (param, reg) ->
        param.id to Pair(param, reg)
    }

    val (arraySizeOps, arraySizeReg) = member.dynamicArraySize.toCgOps(namer+2, globals, newKlassLocals)

    return Pair(loaderOps.flatten() + arraySizeOps, arraySizeReg)
}