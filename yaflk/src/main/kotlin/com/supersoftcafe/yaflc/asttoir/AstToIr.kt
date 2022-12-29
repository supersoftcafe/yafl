package com.supersoftcafe.yaflc.asttoir

import com.supersoftcafe.yaflc.Ast
import com.supersoftcafe.yaflc.Declaration
import com.supersoftcafe.yaflc.Module
import com.supersoftcafe.yaflc.codegen.CgThing


private inline fun <reified TDecl : Declaration, TResult> Ast.forEachDeclaration(
    func: (Module, TDecl) -> List<TResult>,
    filter: (TDecl) -> Boolean = { true }
): List<TResult> {
    return modules.flatMap { module ->
        module.parts.flatMap { part ->
            part.declarations.flatMap { declaration ->
                if (declaration is TDecl && filter(declaration)) {
                    func(module, declaration)
                } else {
                    listOf()
                }
            }
        }
    }
}

fun astToIr(ast: Ast): List<CgThing> {
    ast.forEachDeclaration<Declaration, CgThing>(::assignLlvmName)

    val functions = ast.forEachDeclaration<Declaration.Function, CgThing>(::generateFunction)
//    val classes = ast.forEachDeclaration<Declaration.Struct, CgThing>(::generateClass) { it.onHeap }
    val variables = ast.forEachDeclaration<Declaration.Variable, CgThing>(::generateVariable)

    return listOf(functions, variables).flatten()
}

