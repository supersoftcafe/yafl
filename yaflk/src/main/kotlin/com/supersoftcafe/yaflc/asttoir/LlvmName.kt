package com.supersoftcafe.yaflc.asttoir

import com.supersoftcafe.yaflc.Declaration
import com.supersoftcafe.yaflc.Module
import com.supersoftcafe.yaflc.codegen.CgThing


data class LlvmName(val name: String)


fun assignLlvmName(module: Module, declaration: Declaration): List<CgThing> {
    declaration.stuff += LlvmName(when (declaration) {
        is Declaration.Function ->
            if (declaration.synthetic) declaration.name
            else "f:${module.name}.${declaration.name}+${declaration.type!!}"
        is Declaration.Variable ->
            "v:${module.name}.${declaration.name}+${declaration.type!!}"
        else ->
            "t:${module.name}.${declaration.name}"
    })
    
    return listOf()
}


fun Declaration.asLlvmName() = stuff.firstNotNullOf { (it as? LlvmName)?.name }
