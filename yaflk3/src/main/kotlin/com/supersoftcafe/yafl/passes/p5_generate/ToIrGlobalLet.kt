package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.Expression
import com.supersoftcafe.yafl.models.llir.*
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.tupleOf


fun Declaration.Let.letToIntermediate(namer: Namer, globals: Globals): List<CgThing> {
    val body = body!!
    val globalName = globalDataName()
    val type = typeRef.toCgType(globals)

    if (body is Expression.Characters) {
        // Emit a static string to avoid heap allocation

        val stringClass = globals.type.values.first { it is Declaration.Klass && it.name == "System::String" }
        val stringBytes = body.value.encodeToByteArray()

        return listOf(
            CgThingClassInstance(
                globalName,
                globalTypeName(stringClass.name, stringClass.id),
                listOf(stringBytes.size, stringBytes)
            )
        )

    } else {
        // Emit code to give us the initialisation value
        val (ops, result) = body.toCgOps(namer+1, globals, mapOf())

        // Destructure and store into the global variables
        val destructured = destructureRecursively(namer+2, globals, result).map { (let, value, ops) ->
            if (let.name != "") {
                val globalVar = CgThingVariable(let.globalDataName(), let.typeRef.toCgType(globals))
                tupleOf(globalVar, ops + CgOp.Store(value.type, globalVar.toValue(), value))
            } else {
                tupleOf(null, ops)
            }
        }

        // Extract entries that are real global declarations
        val variables = destructured.mapNotNull { (globalVar, ops) -> globalVar }

        // Put it together into an init function for all the destructured variables associated with this global
        val initFunction = CgThingFunction(
            "init\$$globalName",
            "init",
            type,
            listOf(CgValue.THIS),
            ops + destructured.flatMap { (globalVar, ops) -> ops }
        )

        return variables + listOf(initFunction)
    }
}