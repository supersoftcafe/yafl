package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Either

private class ParseErrorScan : AbstractErrorScan() {

    override fun scanSource(self: TypeRef?, sourceRef: SourceRef): List<String> {
        return super.scanSource(self, sourceRef).ifEmpty {
            when (self) {
                is TypeRef.Array -> {
                    val size = self.size
                    if (size == null)
                        listOf("$sourceRef array size missing")
                    else if (size > Integer.MAX_VALUE.toLong())
                        listOf("$sourceRef array size must be less than ${Integer.MAX_VALUE}")
                    else if (size < 1L)
                        listOf("$sourceRef array size must be greater than zero")
                    else
                        listOf()
                }

                else -> listOf()
            }
        }
    }
}


fun parseErrorScan(ast: Ast): Either<Ast, List<String>> {
    val errors = ParseErrorScan().scan(ast)

    return if (errors.isEmpty())
         Either.Some(ast)
    else Either.Error(errors)
}
