package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Either

private class ParseErrorScan : AbstractScanner<String>() {

    private fun List<Declaration.Let>.testForArrayNotPermitted(): List<String> {
        return mapNotNull { let ->
            let.dynamicArraySize?.let {
                "${let.sourceRef} array specifier not valid here"
            }
        }
    }

    private fun List<Declaration.Let>.testForDefaultValueNotPermitted(): List<String> {
        return mapNotNull { let ->
            let.body?.let {
                "${it.sourceRef} default value not valid here"
            }
        }
    }

    private fun Declaration.testForGenericsNotPermitted(): List<String> {
        return if (scope !is Scope.Global && genericDeclaration.isNotEmpty()) {
            listOf("$sourceRef generic parameters can only be specified on globals")
        } else {
            listOf()
        }
    }

    override fun scanLet(self: Declaration.Let): List<String> {
        return super.scanLet(self).ifEmpty {
            if (self.arraySize != null && (self.arraySize < 1 || self.arraySize > Int.MAX_VALUE)) {
                listOf("${self.sourceRef} array size must be between 1 and ${Int.MAX_VALUE}")
            } else {
                listOf()
            } + self.testForGenericsNotPermitted()
        }
    }

    override fun scanKlass(self: Declaration.Klass): List<String> {
        return super.scanKlass(self).ifEmpty {
            self.parameters.dropLast(1).testForArrayNotPermitted() +
            self.parameters.testForDefaultValueNotPermitted() +
            self.members.mapNotNull {
                if (it.extensionType != null)
                    "${it.sourceRef} extension method is invalid in this context"
                else
                    null
            }
        }
    }

    override fun scanFunction(self: Declaration.Function): List<String> {
        return super.scanFunction(self).ifEmpty {
            self.parameters.testForArrayNotPermitted() +
            self.parameters.testForDefaultValueNotPermitted() +
            self.testForGenericsNotPermitted()
        }
    }

    override fun scan(self: Expression?, parent: Expression?): List<String> {
        return super.scan(self, parent).ifEmpty {
            when (self) {
                is Expression.RawPointer ->
                    if (self.field !is Expression.LoadMember)
                        listOf("${self.sourceRef} raw pointer can only be used with a field access expression")
                    else
                        listOf()

                is Expression.Let ->
                    if (self.let.body == null)
                        listOf("${self.sourceRef} let must have initializer expression" )
                    else
                        listOf()

                is Expression.Lambda ->
                    self.parameters.testForArrayNotPermitted() +
                    self.parameters.testForDefaultValueNotPermitted()

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
