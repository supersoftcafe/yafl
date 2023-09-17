package com.supersoftcafe.yafl.passes.p4_optimise

import com.supersoftcafe.yafl.models.ast.Ast
import com.supersoftcafe.yafl.utils.Either
import com.supersoftcafe.yafl.utils.some


fun optimise(ast: Ast): Either<Ast> {
    return some(lambdaToClass(stringsToGlobals(ast)))
}
