package com.supersoftcafe.yafl.passes.p1_parse

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.models.ast.Ast
import com.supersoftcafe.yafl.models.ast.Root
import com.supersoftcafe.yafl.models.ast.Scope
import com.supersoftcafe.yafl.models.ast.importsOf
import com.supersoftcafe.yafl.utils.*
import java.net.URI

fun parseFileToAst(namer: Namer, file: TextSource): Either<Ast> {
    return file.readContent()
        .map { sourceToParseTree(file.location, it) }
        .map { parseTreeToAst(namer, file.location, it) }
}

private fun parseTreeToAst(namer: Namer, file: URI, tree: YaflParser.RootContext): Either<Ast> {
    val fileName = file.toString()
    val moduleName = tree.module().typeRef().qualifiedName().toName()
    val imports = importsOf(listOf(moduleName) + tree.import_().map { it.typeRef().qualifiedName().toName() })
    val prefix = "$moduleName::"

    // Add all actual declarations from this file
    val declarations = tree.declaration().mapIndexed { index, declaration ->
        val declarations = declaration.toDeclaration(fileName, namer + index, Scope.Global, prefix)
        Root(imports, declarations, fileName)
    }

    return some(Ast(declarations = declarations))
}