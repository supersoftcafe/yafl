package com.supersoftcafe.yaflc.asttoir

import com.supersoftcafe.yaflc.Declaration
import com.supersoftcafe.yaflc.Module
import com.supersoftcafe.yaflc.codegen.CgThing
import com.supersoftcafe.yaflc.codegen.CgThingFunction
import com.supersoftcafe.yaflc.codegen.CgThingVariable


fun generateFunction(module: Module, function: Declaration.Function): List<CgThing> {
    val teturnType = function.result!!.toCgType()
    val parameters = function.parameters
        .mapIndexed { index, param -> Pair(index, param) }
        .associate { (index, param) -> Pair(param, CgThingVariable("p$index", param.type!!.toCgType())) }

    // Register and label numbers use incrementing counter
    // How to do this non-mutably?

}