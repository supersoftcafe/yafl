package com.supersoftcafe.yafl.passes.p1_parse

import com.supersoftcafe.yafl.models.ast.Ast
import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.Expression
import com.supersoftcafe.yafl.passes.AbstractScanner
import com.supersoftcafe.yafl.utils.*

private class ParseErrorScan : AbstractScanner<ErrorInfo>() {

    private fun List<Declaration.Let>.testForArrayNotPermitted(): List<ErrorInfo> {
        return mapNotNull { let ->
            let.dynamicArraySize?.let {
                ErrorInfo.StringWithSourceRef(it.sourceRef, "array specifier not valid here")
            }
        }
    }

    private fun List<Declaration.Let>.testForDefaultValueNotPermitted(): List<ErrorInfo> {
        return mapNotNull { let ->
            let.body?.let {
                ErrorInfo.StringWithSourceRef(it.sourceRef, "default value not valid here")
            }
        }
    }

    override fun scanLet(self: Declaration.Let): List<ErrorInfo> {
        return super.scanLet(self).ifEmpty {
            if (self.arraySize != null && (self.arraySize < 1 || self.arraySize > Int.MAX_VALUE)) {
                listOf(ErrorInfo.StringWithSourceRef(self.sourceRef, "array size must be between 1 and ${Int.MAX_VALUE}"))
            } else {
                listOf()
            }
        }
    }

    override fun scanKlass(self: Declaration.Klass): List<ErrorInfo> {
        return super.scanKlass(self).ifEmpty {
            self.parameters.dropLast(1).testForArrayNotPermitted() +
            self.parameters.testForDefaultValueNotPermitted() +
            self.members.mapNotNull {
                if (it.extensionType != null)
                    ErrorInfo.StringWithSourceRef(it.sourceRef, "extension method is invalid in this context")
                else
                    null
            }
        }
    }

    override fun scanFunction(self: Declaration.Function): List<ErrorInfo> {
        return super.scanFunction(self).ifEmpty {
            self.parameter.flatten().testForDefaultValueNotPermitted()
        }
    }

    override fun scan(self: Expression?, parent: Expression?): List<ErrorInfo> {
        return super.scan(self, parent).ifEmpty {
            when (self) {
                is Expression.RawPointer ->
                    if (self.field !is Expression.LoadMember)
                        listOf(ErrorInfo.StringWithSourceRef(self.sourceRef, "raw pointer can only be used with a field access expression"))
                    else
                        listOf()

                is Expression.Let ->
                    if (self.let.body == null)
                        listOf(ErrorInfo.StringWithSourceRef(self.sourceRef, "let must have initializer expression"))
                    else
                        listOf()

                is Expression.Lambda ->
                    self.parameter.flatten().testForArrayNotPermitted() +
                    self.parameter.flatten().testForDefaultValueNotPermitted()

                else ->
                    listOf()
            }
        }
    }
}


fun parseErrorScan(ast: Ast): Either<Ast> {
    val errors = ParseErrorScan().scan(ast)

    return if (errors.isEmpty())
         some(ast)
    else none(errors)
}
