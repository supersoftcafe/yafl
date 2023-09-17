package com.supersoftcafe.yafl.passes.p1_parse

import com.supersoftcafe.yafl.models.ast.Ast
import com.supersoftcafe.yafl.utils.*


fun parseFilesToAst(files: List<TextSource>): Either<Ast> {
    val namer = Namer("a")

    val results = files.mapIndexed { index, file ->
        parseFileToAst(namer + index, file)
            .map { parseErrorScan(it) }
    }

    val errors = results.flatMap { (it as? None)?.error ?: listOf() }
    return if (errors.isEmpty())
         some(results.mapNotNull { (it as? Some)?.value }.fold(Ast()) { l, r -> l + r })
    else none(errors)
}
