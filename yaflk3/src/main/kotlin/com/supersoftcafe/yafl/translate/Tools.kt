package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.DataRef
import com.supersoftcafe.yafl.ast.Expression
import com.supersoftcafe.yafl.utils.Namer


fun Expression.searchAndReplaceExpressions(updater: (Expression) -> Expression?): Expression {
    return object: AbstractUpdater<Unit>(Unit, { x, y -> Unit } ) {
        override fun updateExpression(self: Expression, path: List<Any>): Pair<Expression, Unit> {
            return updater(self)?.let { it to Unit } ?: super.updateExpression(self, path)
        }
    }.updateExpression(this, listOf()).first
}

fun Expression.findLocalDataReferences(): List<Namer> {
    return object: AbstractScanner<Namer>() {
        override fun scan(self: Expression?, parent: Expression?): List<Namer> {
            return if (self is Expression.LoadData)
                listOfNotNull((self.dataRef as DataRef.Resolved).id)
            else
                super.scan(self, parent)
        }
    }.scan(this, null)
}