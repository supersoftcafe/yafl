package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.Expression
import com.supersoftcafe.yafl.models.ast.TypeRef
import com.supersoftcafe.yafl.models.llir.CgOp
import com.supersoftcafe.yafl.models.llir.CgOps
import com.supersoftcafe.yafl.models.llir.CgValue
import com.supersoftcafe.yafl.models.llir.combineWithPhi
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.tupleOf


fun Expression.When.toWhenCgOps(
    ids: Namer,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>,
): Pair<List<CgOp>, CgValue> {
    // Read final member of struct as discriminator and branch, unpacking enum appropriately

    val (enumExprIds, discriminatorId, branchIds, labelIds, elseIds, destructureIds) = ids.fork()
    val enumInfo = createTaggedValuesInfo(condition.typeRef as TypeRef.TaggedValues, globals)

    val enumExpr = CgOps(condition.toCgOps(enumExprIds, globals, locals))
    val discriminator = CgOps(CgOp.ExtractValue(discriminatorId, enumExpr.result, intArrayOf(enumInfo.transportType.fields.size - 1)))

    val elseBranch = branches.firstOrNull { it.tag == null }?.expression
    val branches = branches.filter { it.tag != null } .mapIndexed { branchIndex, (tag, parameter, expression) ->

        val tagIndex = enumInfo.tagMaps.indexOfFirst { it.tagName == tag }
        if (tagIndex < 0) throw IllegalStateException("Tag did not exist")

        // Re-constitute tag type from transport type
        val enumEntry = enumInfo.tagMaps[tagIndex]
        val (extractOps, tupleResult) = enumEntry.mappings.foldIndexed(tupleOf(listOf<CgOp>(), CgValue.undef(enumEntry.tagType))) { entryIndex, (ops, value), mapping ->
            val regName = "$branchIds.$branchIndex.$entryIndex."
            val extractOp = CgOp.ExtractValue(regName + 'e', enumExpr.result, mapping.originalPath)
            val insertOp = CgOp.InsertValue(regName + 'i', value, mapping.originalPath, extractOp.result)
            tupleOf(ops + extractOp + insertOp, insertOp.result)
        }

        // Destructure tag type into parameters for the value expression
        val destructuredValues = parameter.destructureRecursively(destructureIds + branchIndex, globals, tupleResult)
        val branchLocals = destructuredValues.associate { (let, value, ops) -> let.id to tupleOf(let, value) }
        val destructureOps = destructuredValues.flatMap { (let, value, ops) -> ops }

        // Evaluate expression
        val expressionOps = expression.toCgOps(branchIds + branchIndex, globals, branchLocals)

        val label = CgOp.Label("$branchIds.$branchIndex")
        tupleOf(label,
            CgOps(listOf(label) + extractOps + destructureOps) + expressionOps,
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

