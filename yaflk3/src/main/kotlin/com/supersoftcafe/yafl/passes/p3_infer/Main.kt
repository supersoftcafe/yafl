package com.supersoftcafe.yafl.passes.p3_infer

import com.supersoftcafe.yafl.models.ast.Ast
import com.supersoftcafe.yafl.utils.*


fun inferTypes(ast: Ast): Either<Ast> {
    val result = inferTypes2(ast)
    val errors = inferTypesErrorScan(result)

    return if (errors.isEmpty())
         some(result)
    else none(errors)
}
