package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Ast
import com.supersoftcafe.yafl.utils.*


fun generate(ast: Ast, llFiles: List<TextSource>): Either<String> {
    val intermediate = convertToIntermediate(ast)
    val llvmIr1 = generateLlvmIr(intermediate)
    val llvmIr2 = addCommonCode(llvmIr1, llFiles)
    return llvmIr2
}


fun addCommonCode(content: String, llFiles: List<TextSource>): Either<String> {
    return llFiles
        .map { it.readContent() }
        .allOrNothing()
        .map { some(it.joinToString(separator = "", postfix = content)) }
}
