package com.supersoftcafe.yaflc.asttoir

import com.supersoftcafe.yaflc.Ast
import com.supersoftcafe.yaflc.Declaration
import com.supersoftcafe.yaflc.Module
import com.supersoftcafe.yaflc.codegen.CgThing
import com.supersoftcafe.yaflc.codegen.CgThingFunction


private inline fun <reified TDecl : Declaration, TResult> Ast.forEachDeclaration(func: (Module, TDecl) -> List<TResult>, filter: (TDecl) -> Boolean = { true }): List<TResult> {
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

private fun createMainMethod(variables: List<CgThing>, ast: Ast): CgThingFunction {
    // Call the variable init function for each global variable
    // Call the main method and return the result
}

fun astToIr(ast: Ast): List<CgThing> {
    // Main method must have a specific signature. All others have mangled names.
    val functions = ast.forEachDeclaration<Declaration.Function, CgThing>(::generateFunction)
    val classes = ast.forEachDeclaration<Declaration.Struct, CgThing>(::generateClass) { it.onHeap }
    val variables = ast.forEachDeclaration<Declaration.Variable, CgThing>(::generateVariables)
    val initFunctions = ast.forEachDeclaration<Declaration.Variable, CgThing>(::generateInitFunctions)

    val mainMethod = listOf(createMainMethod(variables, ast))

    return listOf(functions, classes, variables, initFunctions, mainMethod).flatten()
}

