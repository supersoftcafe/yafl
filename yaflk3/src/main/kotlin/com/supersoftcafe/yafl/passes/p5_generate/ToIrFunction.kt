package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.codegen.*
import com.supersoftcafe.yafl.models.llir.*
import com.supersoftcafe.yafl.passes.p5_generate.*
import com.supersoftcafe.yafl.utils.Namer


private fun Declaration.Function.toIntermediateExternalFunction(
    namer: Namer,
    globals: Globals
): List<CgThingExternalFunction> {
    val params = (listOf(thisDeclaration) + parameters).map { param ->
        val paramType = param.typeRef.toCgType(globals)
        CgValue.Register(localName(param.name, param.id), paramType)
    }

    return listOf(
        CgThingExternalFunction(
        globalDataName(),
        name.substringAfterLast("::"),
        typeRef.result!!.toCgType(globals),
        params,
    )
    )
}

private fun Declaration.Function.toIntermediateFunction(
    namer: Namer,
    globals: Globals
): List<CgThingFunction> {
    val body = body!!
    val type = typeRef

    val locals = (listOf(thisDeclaration) + parameters).associate {
        it.id to Pair(it, CgValue.Register(localName(it.name, it.id), it.typeRef!!.toCgType(globals)))
    }

    val (ops, returnValue) = body.toCgOps(namer, globals, locals)

    return listOf(
        CgThingFunction(
        globalDataName(),
        signature!!,
        type.result!!.toCgType(globals),
        locals.values.map { (_, value) -> value },
        ops + CgOp.Return(returnValue)
    )
    )
}

fun Declaration.Function.functionToIntermediate(
    namer: Namer,
    globals: Globals
): List<CgThing> {
    return if ("extern" in attributes)
         toIntermediateExternalFunction(namer, globals)
    else toIntermediateFunction(namer, globals)
}