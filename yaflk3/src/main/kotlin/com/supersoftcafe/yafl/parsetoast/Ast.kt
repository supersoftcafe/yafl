package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Namer


fun parseToAst(namer: Namer, file: String, tree: YaflParser.RootContext): Ast {
    val moduleName = tree.module().typeRef().qualifiedName().toName()
    val imports = importsOf(listOf(moduleName) + tree.import_().map { it.typeRef().qualifiedName().toName() })
    val prefix = "$moduleName::"

//    // Create a module declaration for each prefix module name, only when such a declaration does not exist yet
//    val (declarations1, counter1) = List(moduleName.size) { index -> moduleName.subList(0, index + 1).joinToString(".") }
//        .fold(Pair(listOf<Pair<Imports, Declaration>>(), ast.counter)) { (declarations, tailCounter), moduleName ->
//            if (ast.declarations.any { (_, decl) -> decl.name == moduleName && decl is Declaration.Module })
//                Pair(declarations, tailCounter)
//            else
//                Pair(declarations + Pair(imports, Declaration.Module(moduleName, tailCounter)), tailCounter + 1)
//        }

    // Add all actual declarations from this file
    val declarations = tree.declaration()
        .flatMapIndexed { index, declaration ->
            declaration.toDeclaration(file, namer + index, Scope.Global, prefix).map {
                Root(imports, it, file)
            }
        }

    return Ast(declarations = declarations)
}