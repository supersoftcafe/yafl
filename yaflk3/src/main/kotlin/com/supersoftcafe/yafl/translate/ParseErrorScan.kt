package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Either

private class ParseErrorScan : AbstractErrorScan() {

    override fun scanLet(self: Declaration.Let): List<String> {
        return super.scanLet(self).ifEmpty {
            if (self.arraySize != null && (self.arraySize < 1 || self.arraySize > Int.MAX_VALUE)) {
                listOf("${self.sourceRef} array size must be between 1 and ${Int.MAX_VALUE}")
            } else {
                listOf()
            }
        }
    }

    override fun scanFunction(self: Declaration.Function): List<String> {
        return super.scanFunction(self).ifEmpty {
            self.parameters.flatMap { let ->
                if (let.arraySize != null) {
                    listOf("${let.sourceRef} array specified not valid here")
                } else {
                    listOf()
                }
            }
        }
    }

    override fun scan(self: Expression?, parent: Expression?): List<String> {
        return super.scan(self, parent).ifEmpty {
            when (self) {
                is Expression.Lambda ->
                    self.parameters.flatMap { let ->
                        if (let.arraySize != null) {
                            listOf("${let.sourceRef} array specified not valid here")
                        } else {
                            listOf()
                        }
                    }

                else ->
                    listOf()
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
