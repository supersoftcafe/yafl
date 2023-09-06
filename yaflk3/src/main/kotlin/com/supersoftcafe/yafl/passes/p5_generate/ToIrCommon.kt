package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.Expression
import com.supersoftcafe.yafl.models.llir.CgOp
import com.supersoftcafe.yafl.models.llir.CgTypeStruct
import com.supersoftcafe.yafl.models.llir.CgValue
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.mapFirst
import com.supersoftcafe.yafl.utils.splitIntoTwoLists
import com.supersoftcafe.yafl.utils.tupleOf


fun localName(name: String, id: Namer) = "l$$name$$id"
fun Declaration.Data.globalDataName() = "d$${signature!!}$$id"
fun globalTypeName(name: String, id: Namer) = "t$$name$$id"



fun Expression.evaluateAndExtractTupleFields(
    namer: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>
): Pair<List<CgOp>, List<CgValue>> {
    return if (this is Expression.Tuple) {
        fields.mapIndexed { fieldIndex, tupleField ->
            tupleField.expression.toCgOps(namer + (1 + fieldIndex), globals, locals)
        }.splitIntoTwoLists().mapFirst { it.flatten() }
    } else {
        val (tupleOps, tupleReg) = toCgOps(namer + 0, globals, locals)
        val fields = (tupleReg.type as? CgTypeStruct)?.fields ?: throw IllegalStateException("CgTypeStruct expected")
        val extractOps = fields.mapIndexed { fieldIndex, type ->
            CgOp.ExtractValue(namer + (1 + fieldIndex), tupleReg, intArrayOf(fieldIndex))
        }
        tupleOf(tupleOps + extractOps, extractOps.map { it.result })
    }
}