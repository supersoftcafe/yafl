package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.Expression
import com.supersoftcafe.yafl.codegen.*
import com.supersoftcafe.yafl.models.llir.CgThing
import com.supersoftcafe.yafl.utils.Namer


fun Declaration.Value.letToIntermediate(namer: Namer, globals: Globals): List<CgThing> {
    val body = body!!
    val globalName = globalDataName()
    val type = typeRef.toCgType(globals)

    if (body is Expression.Characters) {
        // Static string

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
        // Variable and init function
        val (ops, result) = body.toCgOps(namer, globals, mapOf())

        return listOf(
            CgThingVariable(globalName, type),
            CgThingFunction(
                "init\$$globalName",
                "init",
                type,
                listOf(CgValue.THIS),
                ops + CgOp.Return(result)
            )
        )
    }
}