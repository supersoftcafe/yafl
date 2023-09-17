package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.Expression
import com.supersoftcafe.yafl.models.ast.TypeRef
import com.supersoftcafe.yafl.models.llir.CgOp
import com.supersoftcafe.yafl.models.llir.CgTypePrimitive
import com.supersoftcafe.yafl.models.llir.CgValue
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.tupleOf


fun Expression.Tag.createTaggedContainerCgOps(
    ids: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    val (paramIds, fieldIds) = ids.fork()

    val runtimeInfo = createTaggedValuesInfo(typeRef as TypeRef.TaggedValues, globals)
    val (valueOps, valueReg) = value.toCgOps(paramIds, globals, locals)

    val mappingEntry = runtimeInfo.tagMaps.first { it.tagName == tag }
    val result = runtimeInfo.transportType.fields.foldIndexed(Pair(valueOps, CgValue.undef(runtimeInfo.transportType))) {
            index, (ops, reg), fieldType ->

        val mapping = mappingEntry.mappings.firstOrNull { it.transportIndex == index }
        val (extractId, insertId) = (fieldIds + index).fork()
        val (extractOp, extractReg) = if (mapping != null) {
            assert(mapping.originalPath.isNotEmpty())
            // Mapped slots should copy from the source tuple
            val extract = CgOp.ExtractValue(extractId.toString(), valueReg, mapping.originalPath)
            tupleOf(extract, extract.result)
        } else if (index == runtimeInfo.transportType.fields.size - 1) {
            // Final slot should be initialised with the tag value
            tupleOf(null, CgValue.Immediate(mappingEntry.tagValue.toString(), CgTypePrimitive.INT8))
        } else if (fieldType == CgTypePrimitive.OBJECT) {
            // Unused object* slots should be initialised with UNIT
            tupleOf(null, CgValue.UNIT)
        } else if (fieldType == CgTypePrimitive.FUNPTR || fieldType == CgTypePrimitive.POINTER) {
            // Unused pointer slots should be initialised with NULL
            tupleOf(null, CgValue.NULL)
        } else {
            // Unused numeric slots should be initialised with 0
            tupleOf(null, CgValue.Immediate("0", fieldType))
        }
        val insertOp = CgOp.InsertValue(insertId.toString(), reg, intArrayOf(index), extractReg)

        Pair(ops + listOfNotNull(extractOp, insertOp), insertOp.result)
    }

    return result
}
