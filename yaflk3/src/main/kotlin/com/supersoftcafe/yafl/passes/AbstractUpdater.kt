@file:Suppress("NAME_SHADOWING")

package com.supersoftcafe.yafl.passes

import com.supersoftcafe.yafl.models.ast.*

abstract class AbstractUpdater<TOut>(private val emptyResult: TOut, private val combineResult: (TOut,TOut)->TOut) {
    private infix operator fun TOut.plus(r: TOut) = combineResult(this, r)


    protected fun <TIn> updateNullable(self: TIn?, path: List<Any>, updater: (TIn, List<Any>) -> Pair<TIn, TOut>): Pair<TIn?, TOut> {
        return self?.let { updater(it, path) } ?: Pair(null, emptyResult)
    }

    protected fun <TIn> updateList(self: List<TIn>, path: List<Any>, updater: (TIn, List<Any>) -> Pair<TIn, TOut>): Pair<List<TIn>, TOut> {
        val list = self.map { updater(it, path) }
        return list.map { (i,_) -> i } to list.fold(emptyResult) { acc,(_,o) -> acc+o }
    }

    protected fun <TKey,TIn> updateMap(self: Map<TKey, TIn>, path: List<Any>, updater: (TIn, List<Any>) -> Pair<TIn, TOut>): Pair<Map<TKey, TIn>, TOut> {
        val map = self.mapValues { updater(it.value, path) }
        return map.mapValues { it.value.first } to map.values.fold(emptyResult) { acc,(_,o) -> acc+o }
    }




    open fun updateSourceTupleTypeField(self: TupleTypeField, path: List<Any>): Pair<TupleTypeField, TOut> {
        val path = path + self
        val (tIn, tOut) = updateNullable(self.typeRef, path, ::updateSourceTypeRef)
        return self.copy(typeRef = tIn) to tOut
    }

    open fun updateSourceTypeRefTuple(self: TypeRef.Tuple, path: List<Any>): Pair<TypeRef.Tuple, TOut> {
        val path = path + self
        val (fIn, fOut) = updateList(self.fields, path, ::updateSourceTupleTypeField)
        return self.copy(fields = fIn) to fOut
    }

    open fun updateSourceTagTypeField(self: TagTypeField, path: List<Any>): Pair<TagTypeField, TOut> {
        val path = path + self
        val (tIn, tOut) = updateTypeRefTuple(self.typeRef, path)
        return self.copy(typeRef = tIn) to tOut
    }

    open fun updateSourceTypeRefTags(self: TypeRef.TaggedValues, path: List<Any>): Pair<TypeRef.TaggedValues, TOut> {
        val path = path + self
        val (tIn, tOut) = updateList(self.tags, path, ::updateSourceTagTypeField)
        return self.copy(tags = tIn) to tOut
    }

    open fun updateSourceTypeRefCallable(self: TypeRef.Callable, path: List<Any>): Pair<TypeRef.Callable, TOut> {
        val path = path + self
        val (rIn, rOut) = updateNullable(self.result, path, ::updateSourceTypeRef)
        val (pIn, pOut) = updateNullable(self.parameter, path, ::updateSourceTypeRef)
        return self.copy(result = rIn, parameter = pIn) to rOut+pOut
    }

    open fun updateSourceTypeRefKlass(self: TypeRef.Klass, path: List<Any>): Pair<TypeRef.Klass, TOut> {
        val path = path + self
        val (eIn, eOut) = updateList(self.extends, path, ::updateSourceTypeRefKlass)
        return self.copy(extends = eIn) to eOut
    }

    open fun updateSourceTypeRefPrimitive(self: TypeRef.Primitive, path: List<Any>): Pair<TypeRef.Primitive, TOut> {
        return self to emptyResult
    }

    open fun updateSourceTypeRefUnresolved(self: TypeRef.Unresolved, path: List<Any>): Pair<TypeRef.Unresolved, TOut> {
        return self to emptyResult
    }

    open fun updateSourceTypeRef(self: TypeRef, path: List<Any>): Pair<TypeRef, TOut> {
        return when (self) {
            is TypeRef.Tuple        -> updateSourceTypeRefTuple(     self, path)
            is TypeRef.TaggedValues -> updateSourceTypeRefTags(      self, path)
            is TypeRef.Callable     -> updateSourceTypeRefCallable(  self, path)
            is TypeRef.Klass        -> updateSourceTypeRefKlass(     self, path)
            is TypeRef.Primitive    -> updateSourceTypeRefPrimitive( self, path)
            is TypeRef.Unresolved   -> updateSourceTypeRefUnresolved(self, path)
        }
    }


    open fun updateTupleTypeField(self: TupleTypeField, path: List<Any>): Pair<TupleTypeField, TOut> {
        val path = path + self
        val (tIn, tOut) = updateNullable(self.typeRef, path, ::updateTypeRef)
        return self.copy(typeRef = tIn) to tOut
    }

    open fun updateTypeRefTuple(self: TypeRef.Tuple, path: List<Any>): Pair<TypeRef.Tuple, TOut> {
        val path = path + self
        val (fIn, fOut) = updateList(self.fields, path, ::updateTupleTypeField)
        return self.copy(fields = fIn) to fOut
    }

    open fun updateTagTypeField(self: TagTypeField, path: List<Any>): Pair<TagTypeField, TOut> {
        val path = path + self
        val (tIn, tOut) = updateTypeRefTuple(self.typeRef, path)
        return self.copy(typeRef = tIn) to tOut
    }

    open fun updateTypeRefTags(self: TypeRef.TaggedValues, path: List<Any>): Pair<TypeRef.TaggedValues, TOut> {
        val path = path + self
        val (tIn, tOut) = updateList(self.tags, path, ::updateTagTypeField)
        return self.copy(tags = tIn) to tOut
    }

    open fun updateTypeRefCallable(self: TypeRef.Callable, path: List<Any>): Pair<TypeRef.Callable, TOut> {
        val path = path + self
        val (rIn, rOut) = updateNullable(self.result, path, ::updateTypeRef)
        val (pIn, pOut) = updateNullable(self.parameter, path, ::updateTypeRef)
        return self.copy(result = rIn, parameter = pIn) to rOut+pOut
    }

    open fun updateTypeRefKlass(self: TypeRef.Klass, path: List<Any>): Pair<TypeRef.Klass, TOut> {
        val path = path + self
        val (eIn, eOut) = updateList(self.extends, path, ::updateTypeRefKlass)
        return self.copy(extends = eIn) to eOut
    }

    open fun updateTypeRefPrimitive(self: TypeRef.Primitive, path: List<Any>): Pair<TypeRef.Primitive, TOut> {
        return self to emptyResult
    }

    open fun updateTypeRefUnresolved(self: TypeRef.Unresolved, path: List<Any>): Pair<TypeRef.Unresolved, TOut> {
        return self to emptyResult
    }

    open fun updateTypeRef(self: TypeRef, path: List<Any>): Pair<TypeRef, TOut> {
        return when (self) {
            is TypeRef.Tuple        -> updateTypeRefTuple(self, path)
            is TypeRef.TaggedValues -> updateTypeRefTags(self, path)
            is TypeRef.Callable     -> updateTypeRefCallable(self, path)
            is TypeRef.Klass        -> updateTypeRefKlass(self, path)
            is TypeRef.Primitive    -> updateTypeRefPrimitive(self, path)
            is TypeRef.Unresolved   -> updateTypeRefUnresolved(self, path)
        }
    }


    open fun updateDataRefUnresolved(self: DataRef.Unresolved, path: List<Any>): Pair<DataRef.Unresolved, TOut> {
        return self to emptyResult
    }

    open fun updateDataRefResolved(self: DataRef.Resolved, path: List<Any>): Pair<DataRef.Resolved, TOut> {
        return self to emptyResult
    }

    open fun updateDataRef(self: DataRef, path: List<Any>): Pair<DataRef, TOut> {
        return when (self) {
            is DataRef.Resolved -> updateDataRefResolved(self, path)
            is DataRef.Unresolved -> updateDataRefUnresolved(self, path)
        }
    }


    open fun updateExpressionRawPointer(self: Expression.RawPointer, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = updateTypeRef(self.typeRef, path)
        val (fIn, fOut) = updateExpression(self.field, path)
        return self.copy(typeRef = tIn as TypeRef.Primitive, field = fIn) to tOut+fOut
    }

    open fun updateExpressionLet(self: Expression.Let, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (lIn, lOut) = updateDeclarationLet(self.let, path)
        val (eIn, eOut) = updateExpression(self.tail, path)
        return self.copy(typeRef = tIn, let = lIn, tail = eIn) to tOut+lOut+eOut
    }

    open fun updateExpressionArrayLookup(self: Expression.ArrayLookup, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (aIn, aOut) = updateExpression(self.array, path)
        val (iIn, iOut) = updateExpression(self.index, path)
        return self.copy(typeRef = tIn, array = aIn, index = iIn) to tOut+aOut+iOut
    }

    open fun updateExpressionAssert(self: Expression.Assert, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (cIn, cOut) = updateExpression(self.condition, path)
        val (vIn, vOut) = updateExpression(self.value, path)
        return self.copy(typeRef = tIn, condition = cIn, value = vIn) to tOut+cOut+vOut
    }

    open fun updateExpressionCall(self: Expression.Call, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (cIn, cOut) = updateExpression(self.callable, path)
        val (pIn, pOut) = updateExpression(self.parameter, path)
        return self.copy(typeRef = tIn, callable = cIn, parameter = pIn) to tOut+cOut+pOut
    }

    open fun updateExpressionParallel(self: Expression.Parallel, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (pIn, pOut) = updateExpressionTuple(self.parameter, path)
        return self.copy(typeRef = tIn, parameter = pIn) to tOut+pOut
    }

    open fun updateExpressionCharacters(self: Expression.Characters, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = updateTypeRef(self.typeRef, path)
        return self.copy(typeRef = tIn) to tOut
    }

    open fun updateExpressionFloat(self: Expression.Float, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = updateTypeRef(self.typeRef, path)
        return self.copy(typeRef = tIn) to tOut
    }

    open fun updateExpresionWhenBranch(self: WhenBranch, path: List<Any>): Pair<WhenBranch, TOut> {
        val (xIn, xOut) = updateExpression(self.expression, path)
        val (yIn, yOut) = updateDeclarationLet(self.parameter, path)
        return self.copy(expression = xIn, parameter = yIn) to xOut+yOut
    }

    open fun updateExpressionWhen(self: Expression.When, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (cIn, cOut) = updateExpression(self.condition, path)
        val (eIn, eOut) = updateList(self.branches, path, ::updateExpresionWhenBranch)
        return self.copy(typeRef = tIn, condition = cIn, branches = eIn) to tOut+cOut+eOut
    }

    open fun updateExpressionIf(self: Expression.If, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (cIn, cOut) = updateExpression(self.condition, path)
        val (iIn, iOut) = updateExpression(self.ifTrue, path)
        val (eIn, eOut) = updateExpression(self.ifFalse, path)
        return self.copy(typeRef = tIn, condition = cIn, ifTrue = iIn, ifFalse = eIn) to tOut+cOut+iOut+eOut
    }

    open fun updateExpressionInteger(self: Expression.Integer, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = updateTypeRef(self.typeRef, path)
        return self.copy(typeRef = tIn) to tOut
    }

    open fun updateExpressionLambda(self: Expression.Lambda, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (pIn, pOut) = updateDeclarationLet(self.parameter, path)
        val (bIn, bOut) = updateExpression(self.body, path)
        return self.copy(typeRef = tIn, parameter = pIn, body = bIn) to tOut+pOut+bOut
    }

    open fun updateExpressionLlvmir(self: Expression.Llvmir, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = updateTypeRef(self.typeRef, path)
        val (iIn, iOut) = updateList(self.inputs, path, ::updateExpression)
        return self.copy(typeRef = tIn, inputs = iIn) to tOut+iOut
    }

    open fun updateExpressionLoadData(self: Expression.LoadData, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (dIn, dOut) = updateDataRef(self.dataRef, path)
        return self.copy(typeRef = tIn, dataRef = dIn) to tOut+dOut
    }

    open fun updateExpressionLoadMember(self: Expression.LoadMember, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (bIn, bOut) = updateExpression(self.base, path)
        return self.copy(typeRef = tIn, base = bIn) to tOut+bOut
    }

    open fun updateExpressionNewKlass(self: Expression.NewKlass, path: List<Any>): Pair<Expression, TOut> {
        val path = path + self
        val (tIn, tOut) = updateTypeRef(self.typeRef, path)
        val (pIn, pOut) = updateExpression(self.parameter, path)
        return self.copy(typeRef = tIn, parameter = pIn) to tOut+pOut
    }

    open fun updateTupleExpressionField(self: TupleExpressionField, path: List<Any>): Pair<TupleExpressionField, TOut> {
        val path = path + self
        val (eIn, eOut) = updateExpression(self.expression, path)
        return self.copy(expression = eIn) to eOut
    }

    open fun updateExpressionTuple(self: Expression.Tuple, path: List<Any>): Pair<Expression.Tuple, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (fIn, fOut) = updateList(self.fields, path, ::updateTupleExpressionField)
        return self.copy(typeRef = tIn, fields = fIn) to tOut+fOut
    }

    open fun updateExpressionTag(self: Expression.Tag, path: List<Any>): Pair<Expression.Tag, TOut> {
        val path = path + self
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (vIn, vOut) = updateExpression(self.value, path)
        return self.copy(typeRef = tIn, value = vIn) to tOut+vOut
    }

    open fun updateExpression(self: Expression, path: List<Any>): Pair<Expression, TOut> {
        return when (self) {
            is Expression.RawPointer -> updateExpressionRawPointer(self, path)
            is Expression.Let -> updateExpressionLet(self, path)
            is Expression.ArrayLookup -> updateExpressionArrayLookup(self, path)
            is Expression.Assert -> updateExpressionAssert(self, path)
            is Expression.Call -> updateExpressionCall(self, path)
            is Expression.Parallel -> updateExpressionParallel(self, path)
            is Expression.Characters -> updateExpressionCharacters(self, path)
            is Expression.Float -> updateExpressionFloat(self, path)
            is Expression.When -> updateExpressionWhen(self, path)
            is Expression.If -> updateExpressionIf(self, path)
            is Expression.Integer -> updateExpressionInteger(self, path)
            is Expression.Lambda -> updateExpressionLambda(self, path)
            is Expression.Llvmir -> updateExpressionLlvmir(self, path)
            is Expression.LoadData -> updateExpressionLoadData(self, path)
            is Expression.LoadMember -> updateExpressionLoadMember(self, path)
            is Expression.NewKlass -> updateExpressionNewKlass(self, path)
            is Expression.Tag -> updateExpressionTag(self, path)
            is Expression.Tuple -> updateExpressionTuple(self, path)
        }
    }

    open fun updateDeclarationLet(self: Declaration.Let, path: List<Any>): Pair<Declaration.Let, TOut> {
        val path = path + self
        val (sIn, sOut) = self.sourceTypeRef?.let { updateSourceTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (bIn, bOut) = self.body?.let { updateExpression(it, path) } ?: Pair(null, emptyResult)
        val (tIn, tOut) = self.typeRef?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (dIn, dOut) = self.dynamicArraySize?.let { updateExpression(it, path) } ?: Pair(null, emptyResult)
        val (xIn, xOut) = updateList(self.destructure, path, ::updateDeclarationLet)
        return self.copy(
            sourceTypeRef = sIn,
            body = bIn, typeRef = tIn,
            dynamicArraySize = dIn,
            destructure = xIn
        ) to sOut+bOut+tOut+dOut+xOut
    }

    open fun updateDeclarationFunction(self: Declaration.Function, path: List<Any>): Pair<Declaration.Function, TOut> {
        val path = path + self
        val (sIn, sOut) = self.sourceReturnType?.let { updateSourceTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (pIn, pOut) = updateDeclarationLet(self.parameter, path)
        val (tIn, tOut) = updateDeclarationLet(self.thisDeclaration, path)
        val (rIn, rOut) = self.returnType?.let { updateTypeRef(it, path) } ?: Pair(null, emptyResult)
        val (bIn, bOut) = self.body?.let { updateExpression(it, path) } ?: Pair(null, emptyResult)
        return self.copy(sourceReturnType = sIn, parameter = pIn, thisDeclaration = tIn, returnType = rIn, body = bIn) to sOut+pOut+tOut+rOut+bOut
    }

    open fun updateDeclarationKlass(self: Declaration.Klass, path: List<Any>): Pair<Declaration.Klass, TOut> {
        val path = path + self
        val (mIn, mOut) = updateList(self.members, path, ::updateDeclarationFunction)
        val (pIn, pOut) = updateList(self.parameters, path, ::updateDeclarationLet)
        val (eIn, eOut) = updateList(self.extends, path, ::updateTypeRef)
        return self.copy(members = mIn, parameters = pIn, extends = eIn) to mOut+pOut+eOut
    }

    open fun updateDeclarationAlias(self: Declaration.Alias, path: List<Any>): Pair<Declaration.Alias, TOut> {
        val path = path + self
        val (tIn, tOut) = updateTypeRef(self.typeRef, path)
        return self.copy(typeRef = tIn) to tOut
    }

    open fun updateDeclaration(self: Declaration, path: List<Any>): Pair<Declaration, TOut> {
        return when (self) {
            is Declaration.Let      -> updateDeclarationLet(self, path)
            is Declaration.Function -> updateDeclarationFunction(self, path)
            is Declaration.Alias    -> updateDeclarationAlias(self, path)
            is Declaration.Klass    -> updateDeclarationKlass(self, path)
        }
    }

    open fun updateRoot(self: Root, path: List<Any>): Pair<Root, TOut> {
        val path = path + self
        val (dIn, dOut) = updateList(self.declarations, path, ::updateDeclaration)
        return self.copy(declarations = dIn) to dOut
    }

    open fun updateHint(self: TypeHint, path: List<Any>): Pair<TypeHint, TOut> {
        return Pair(self, emptyResult)
    }

    open fun updateTypeHints(self: TypeHints, path: List<Any>): Pair<TypeHints, TOut> {
        val path = path + self
        val (lIn, lOut) = updateMap(self.lookup, path) { l,p -> updateList(l, p, ::updateHint) }
        return self.copy(lookup = lIn) to lOut
    }

    open fun update(self: Ast): Pair<Ast, TOut> {
        val path = listOf(self)
        val (dIn, dOut) = updateList(self.declarations, path, ::updateRoot)
        val (hIn, hOut) = updateTypeHints(self.typeHints, path)
        return self.copy(declarations = dIn, typeHints = hIn) to dOut+hOut
    }
}