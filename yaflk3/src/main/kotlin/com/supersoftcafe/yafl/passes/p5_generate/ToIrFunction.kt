package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.llir.*
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.tupleOf


private fun Declaration.Function.toIntermediateExternalFunction(
    namer: Namer,
    globals: Globals
): List<CgThingExternalFunction> {
    assert(parameter.destructure.isNotEmpty())
    assert(parameter.destructure.all { it.destructure.isEmpty() })

    val params = (listOf(thisDeclaration) + parameter.destructure).map { param ->
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
    assert(body != null)
    assert(parameter.destructure.isNotEmpty())
    assert(parameter.destructure.all { it.typeRef?.complete == true })

    val body = body!!
    val params = (listOf(thisDeclaration) + parameter.destructure).map {
        tupleOf(it, CgValue.Register(localName(it.name, it.id), it.typeRef!!.toCgType(globals)), listOf<CgOp>())
    }
    val destructuredParams = params.flatMapIndexed { index, (let, register, ops) ->
        let.destructureRecursively(namer + index, globals, register)
    }

    val (ops, returnValue) = body.toCgOps(namer, globals, (params + destructuredParams).associate { (let, register, ops) ->
        let.id to tupleOf(let, register)
    })

    return listOf(
        CgThingFunction(
            globalDataName(),
            signature!!,
            typeRef.result!!.toCgType(globals),
            params.map { (let, register, ops) -> register },
            destructuredParams.flatMap { (let, register, ops) -> ops } + ops + CgOp.Return(returnValue)
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