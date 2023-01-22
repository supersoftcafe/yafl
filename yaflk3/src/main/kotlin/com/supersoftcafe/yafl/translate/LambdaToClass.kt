package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Namer

class LambdaToClass : AbstractUpdater<List<Declaration>>(emptyList(), { l,r -> l+r }) {




    override fun updateExpressionLambda(
        self: Expression.Lambda,
        path: List<Any>
    ): Pair<Expression, List<Declaration>> {
        // Lower lambdas to something that we can codegen more easily.
        // This is done by generating appropriate class or global function and
        // replacing the lambda with a reference to the function. In some cases
        // this requires capture of local values.

        // All constructed declarations must be completely correct, as this is
        // a late stage in compilation and no more inference or validation will
        // happen.


        val owner = path.firstNotNullOf { it as? Declaration.Data }     // Which fun/let is the owner fo the containing expression
        val localLets = path.mapNotNull { (it as? Expression.Let)?.let }
        val localParams = path.firstNotNullOfOrNull { it as? Declaration.Function }?.let { it.parameters + it.thisDeclaration } ?: listOf()
        val locals = (localLets + localParams).associateBy { it.id }    // What are all available locals
        val references = self.body.findLocalDataReferences().toSet()    // Which locals does the lambda reference
        val captures = locals.filterKeys { it in references }           // Which locals do we need to capture
        val lambdaName = "Lambda\$${owner.name}\$${self.id}"



        // If it captures nothing, convert the lambda to a global function
        if (captures.isEmpty()) {

            val globalFunc = Declaration.Function(
                sourceRef = self.sourceRef,
                name = lambdaName,
                id = self.id,
                scope = Scope.Global,
                parameters = self.parameters,
                returnType = self.body.typeRef,
                sourceReturnType = null,
                body = self.body,
                thisDeclaration = Declaration.Let(
                    sourceRef = self.sourceRef,
                    name = "this",
                    id = self.id + 1,
                    scope = Scope.Local,
                    typeRef = TypeRef.Unit,
                    sourceTypeRef = null,
                    body = null))

            val loadExpr = Expression.LoadData(
                sourceRef = self.sourceRef,
                typeRef = self.typeRef,
                dataRef = DataRef.Resolved(
                    name = globalFunc.name,
                    id = globalFunc.id,
                    scope = globalFunc.scope))

            return loadExpr to listOf(globalFunc)
        }

        // If it only needs to capture one local value, and it's a class/interface, convert the lambda to an extension function
        else if (captures.values.singleOrNull()?.typeRef is TypeRef.Named) {
            val local = captures.values.single()
            val thisId = self.id + 1

            val globalFunc = Declaration.Function(
                sourceRef = self.sourceRef,
                name = lambdaName,
                id = self.id,
                scope = Scope.Global,
                parameters = self.parameters,
                returnType = self.body.typeRef,
                sourceReturnType = null,
                body = self.body.searchAndReplaceExpressions {
                    if (it is Expression.LoadData && (it.dataRef as? DataRef.Resolved)?.id == local.id)
                         it.copy(dataRef = DataRef.Resolved("this", thisId, Scope.Local))
                    else null },
                thisDeclaration = Declaration.Let(
                    sourceRef = self.sourceRef,
                    name = "this",
                    id = thisId,
                    scope = Scope.Local,
                    typeRef = local.typeRef,
                    sourceTypeRef = null,
                    body = null))

            val loadExpr = Expression.LoadMember(
                sourceRef = self.sourceRef,
                typeRef = self.typeRef,
                name = globalFunc.name,
                id = globalFunc.id,
                base = Expression.LoadData(
                    sourceRef = self.sourceRef,
                    typeRef = local.typeRef,
                    dataRef = DataRef.Resolved("this", thisId, Scope.Local)))

            return loadExpr to listOf(globalFunc)
        }

        // Otherwise, convert it to a class that captures locals and has a single function to represent the lambda
        else {
            val klassId = self.id + 1
            val memberId = self.id + 2
            val memberThisId = self.id + 3
            val parametersBaseId = self.id + 4

            val klassParameters = captures.values.mapIndexed { index, let ->
                let to Declaration.Let(
                    sourceRef = let.sourceRef,
                    name = "capture\$${let.name}\$$index",
                    id = parametersBaseId + index,
                    scope = Scope.Member(klassId, 0),
                    typeRef = let.typeRef,
                    sourceTypeRef = null,
                    body = null)
            }

            val klassType = TypeRef.Named(
                name = lambdaName,
                id = klassId,
                extends = listOf())

            val memberFunc = Declaration.Function(
                sourceRef = self.sourceRef,
                name = "invoke",
                id = memberId,
                scope = Scope.Global,
                parameters = self.parameters,
                returnType = self.body.typeRef,
                sourceReturnType = null,
                body = self.body.searchAndReplaceExpressions { expr ->
                    if (expr is Expression.LoadData && expr.dataRef is DataRef.Resolved) {
                        klassParameters.firstOrNull { (s,t) -> s.id == expr.dataRef.id }?.let { (s,t) ->
                            Expression.LoadMember(
                                sourceRef = s.sourceRef,
                                typeRef = t.typeRef,
                                name = t.name,
                                id = t.id,
                                base = Expression.LoadData(
                                    sourceRef = s.sourceRef,
                                    typeRef = klassType,
                                    dataRef = DataRef.Resolved(
                                        name = "this",
                                        id = memberThisId,
                                        scope = Scope.Local)))
                        }
                    } else {
                        null
                    }
                },
                thisDeclaration = Declaration.Let(
                    sourceRef = self.sourceRef,
                    name = "this",
                    id = memberThisId,
                    scope = Scope.Local,
                    typeRef = klassType,
                    sourceTypeRef = null,
                    body = null))

            val klass = Declaration.Klass(
                sourceRef = self.sourceRef,
                name = lambdaName,
                id = klassId,
                scope = Scope.Global,
                parameters = klassParameters.map { (s,t) -> t },
                members = listOf(memberFunc),
                extends = listOf(),
                isInterface = false)

            val loadExpr = Expression.LoadMember(
                sourceRef = self.sourceRef,
                typeRef = self.typeRef,
                name = memberFunc.name,
                id = memberFunc.id,
                base = Expression.NewKlass(
                    sourceRef = self.sourceRef,
                    typeRef = klassType,
                    parameter = Expression.Tuple(
                        sourceRef = self.sourceRef,
                        fields = klassParameters.map { (s,t) ->
                            TupleExpressionField(
                                name = null,
                                expression = Expression.LoadData(
                                    sourceRef = self.sourceRef,
                                    typeRef = t.typeRef,
                                    dataRef = DataRef.Resolved(
                                        name = s.name,
                                        id = s.id,
                                        scope = s.scope))) },
                        typeRef = TypeRef.Tuple(
                            fields = klassParameters.map { (s,t) ->
                                TupleTypeField(
                                    name = null,
                                    typeRef = t.typeRef) }))))

            return loadExpr to listOf(klass)
        }
    }
}


fun lambdaToClass(ast: Ast): Ast {
    val (newAst, newDeclarations) = LambdaToClass().update(ast)
    val ast2 = newAst.copy(declarations = newAst.declarations + newDeclarations.map { Root(importsOf(), it, "") })

    if (ast2 != ast)
        return lambdaToClass(ast2)
    else
        return ast2
}
