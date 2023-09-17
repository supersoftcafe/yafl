package com.supersoftcafe.yafl.passes.p2_resolve

import com.supersoftcafe.yafl.models.ast.Ast
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.some


fun resolveTypes(ast: Ast): Either<Ast> {
    val result = ResolveTypes().resolveTypes(ast)
    val errors = resolveTypesErrorScan(result)

    return if (errors.isEmpty())
         some(result)
    else error(errors)
}
