package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.Expression
import com.supersoftcafe.yafl.models.ast.TypeRef
import com.supersoftcafe.yafl.models.llir.*
import com.supersoftcafe.yafl.passes.p5_generate.*
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.tupleOf


fun Declaration.Enum.enumToIntermediate(
    ids: Namer,
    globals: Globals
): List<CgThing> {
    return listOf()
}

fun Expression.NewEnum.toNewEnumCgOps(
    ids: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    val (paramIds, fieldIds) = ids.fork()

    val runtimeInfo = globals.enumInfo[(typeRef as TypeRef.Enum).id]!!.value
    val (valueOps, valueReg) = parameter.toCgOps(paramIds, globals, locals)

    val mappingEntry = runtimeInfo.tagMaps.first { it.tagName == tag }
    val result = runtimeInfo.transportType.fields.foldIndexed(Pair(valueOps, CgValue.undef(runtimeInfo.transportType))) {
            index, (ops, reg), fieldType ->

        val mapping = mappingEntry.mappings.firstOrNull { it.transportIndex == index }
        val (extractId, insertId) = (fieldIds + index).fork()
        val (extractOp, extractReg) = if (mapping != null) {
            // Mapped slots should copy from the source tuple
            val extract = CgOp.ExtractValue(extractId.toString(), valueReg, mapping.originalIndex)
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

fun Expression.When.toWhenCgOps(
    ids: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    // Read final member of struct as discriminator and branch, unpacking enum appropriately

    val (enumExprIds, discriminatorId, branchIds, labelIds, elseIds, phiId) = ids.fork()
    val enumInfo = globals.enumInfo[(typeRef as TypeRef.Enum).id]!!.value

    val enumExpr = CgOps(enumExpression.toCgOps(enumExprIds, globals, locals))
    val discriminator = CgOps(CgOp.ExtractValue(discriminatorId, enumExpr.result, intArrayOf(enumInfo.transportType.fields.size - 1)))

    val elseBranch = branches.firstOrNull { it.tag == null }?.expression
    val branches = branches.filter { it.tag != null } .mapIndexed { branchIndex, (tag, parameter, expression) ->
        val parameters = parameter.destructure

        val tagIndex = enumInfo.tagMaps.indexOfFirst { it.tagName == tag }
        if (tagIndex < 0) throw IllegalStateException("Tag did not exist")

        val enumEntry = enumInfo.tagMaps[tagIndex]
        val extractOps = enumEntry.mappings.mapIndexed { entryIndex, mapping ->
            CgOp.ExtractValue("$branchIds.$branchIndex.$entryIndex", enumExpr.result, mapping.originalIndex)
        }

        val branchLocals = locals + extractOps.zip(parameters).associate { (extractOp, parameter) ->
            parameter.id to Pair(parameter, extractOp.result)
        }

        val label = CgOp.Label("$branchIds.$branchIndex")
        tupleOf(label,
            CgOps(listOf(label) + extractOps) + expression.toCgOps(branchIds + branchIndex, globals, branchLocals),
            tagIndex)
    }

    val elseLabel = CgOp.Label("$labelIds.else")
    val elseOps = if (elseBranch != null) {
        CgOps(elseLabel) + CgOps(elseBranch.toCgOps(elseIds, globals, locals))
    } else {
        CgOps(elseLabel) + CgOp.Assert(CgValue.TRUE, "Corrupt enum")
    }

    val phiOps = combineWithPhi(branches.map { (_, ops, _) -> ops } + elseOps)
    val discriminatorToLabelMap = branches.map { (label, _, tag) -> tag to label.name }
    val switchOp = CgOp.Switch(discriminator.result, elseLabel.name, discriminatorToLabelMap)
    val result = CgOps(switchOp) + phiOps

    return result.ops to result.result
}




class EnumExtractEntry(
    val transportIndex: Int,
    val originalIndex: IntArray,
    val originalType: CgTypePrimitive
)

class EnumTypeEntry(
    val tagName: String,
    val tagValue: Int,
    val tagType: CgTypeStruct,
    val mappings: List<EnumExtractEntry>
)

class EnumRuntimeInfo(
    val transportType: CgTypeStruct,
    val tagMaps: List<EnumTypeEntry>
)

// Convert to transport tuple representation
fun createEnumInfo(declaration: Declaration.Enum, globals: Globals): EnumRuntimeInfo {
    fun CgType.findAllPrimitives(pathPrefix: IntArray = intArrayOf()): List<Pair<CgTypePrimitive, IntArray>> {
        return when (this) {
            is CgTypePrimitive -> listOf(Pair(this, pathPrefix))
            is CgTypeStruct -> fields.flatMapIndexed { index, type -> type.findAllPrimitives(pathPrefix + index) }
            else -> throw IllegalArgumentException("Cannot flatten $this")
        }
    }

    fun List<Pair<CgTypePrimitive, IntArray>>.indexUniqueInstances(): List<Pair<Pair<CgTypePrimitive, Int>, IntArray>> {
        return map { it.first }.distinct().flatMap { instance ->
            filter { it.first == instance }.mapIndexed { index, (type, path) -> Pair(Pair(type, index), path) }
        }
    }

    val analysedMembers = declaration.members.map { (name, type) ->
        val tagType = CgTypeStruct(type.map { it.typeRef.toCgType(globals) })
        val mapping = tagType.findAllPrimitives().indexUniqueInstances()
        tupleOf(name, tagType, mapping)
    }

    val transportSlotsInOrder = analysedMembers
        .flatMap { (tagName, tagType, mapping) -> mapping.map { (typeSlot, path) -> typeSlot }}
        .distinct().sortedWith(compareBy({it.first},{it.second}))

    return EnumRuntimeInfo(
        transportType = CgTypeStruct(transportSlotsInOrder.map { it.first } + CgTypePrimitive.INT8),
        tagMaps = analysedMembers.mapIndexed { index, (tagName, tagType, fields) ->
            EnumTypeEntry(tagName, index, tagType, fields.map { ( typeSlot, path) ->
                EnumExtractEntry(
                    transportIndex = transportSlotsInOrder.indexOf(typeSlot),
                    originalIndex = path,
                    originalType = typeSlot.first
                )
            })
        }
    )
}

fun Declaration.Enum.toCgTypeEnum(
    globals: Globals
): CgTypeStruct {
    return globals.enumInfo[id]!!.value.transportType
}
