package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.mapFirst


// Each use of a declaration (data or type) with given concrete type parameters must have a specialised
// form. Specialization happens over three phases:
//  1. Discovery: Find uses of generic declarations that have concrete type parameters
//  2. Specialization: Create specializations of each generic declaration with the discovered type parameters
//  3. Re-write call sites: Uses of these generics must be replaced with uses of the specialised forms
// These phases can occur out of order, so long as they iterate until there is no more to do.
// Finally, remove original generic declarations, when re-writing is done.


// Replace all uses of generic declarations with references to their specialized counterparts, where known
private fun replaceConcreteGenericReferences(
    ast: Ast,
    targets: Map<Pair<Namer, List<TypeRef>>, Namer>
) = object: AbstractUpdater<List<Unit>>(emptyList(), { l, r -> l+r }) {

    override fun updateTypeRefKlass(
        self: TypeRef.Klass,
        path: List<Any>
    ): Pair<TypeRef.Klass, List<Unit>> {
        val replacementId = targets[self.id to self.genericParameters]
        return if (replacementId != null) {
            self.copy(id = replacementId, genericParameters = listOf())
        } else {
            self
        } to listOf()
    }

    override fun updateDataRefResolved(
        self: DataRef.Resolved,
        path: List<Any>
    ): Pair<DataRef.Resolved, List<Unit>> {
        val replacementId = targets[self.id to self.genericParameters]
        return if (replacementId != null) {
            self.copy(id = replacementId, genericParameters = listOf())
        } else {
            self
        } to listOf()
    }
}.update(ast).first


// Find all concrete uses of generic declarations where the type parameters are well-defined
private fun findConcreteGenericReferences(
    ast: Ast
) = object: AbstractScanner<Pair<Namer, List<TypeRef>>>() {

    override fun scan(
        self: DataRef?,
        sourceRef: SourceRef
    ): List<Pair<Namer, List<TypeRef>>> {
        return super.scan(self, sourceRef) + when (self) {
            is DataRef.Resolved ->
                if (self.genericParameters.isNotEmpty() && self.genericParameters.none { it.hasGenerics }) {
                    listOf(self.id to self.genericParameters)
                } else {
                    listOf()
                }

            is DataRef.Unresolved, null ->
                listOf()
        }
    }

    override fun scan(
        self: TypeRef?,
        sourceRef: SourceRef
    ): List<Pair<Namer, List<TypeRef>>> {
        return super.scan(self, sourceRef) + when (self) {
            is TypeRef.Klass ->
                if (self.genericParameters.isNotEmpty() && self.genericParameters.none { it.hasGenerics }) {
                    listOf(self.id to self.genericParameters)
                } else {
                    listOf()
                }

            is TypeRef.Callable, is TypeRef.Generic, is TypeRef.Primitive, is TypeRef.Tuple, is TypeRef.Unresolved, TypeRef.Unit, null ->
                listOf()
        }
    }
}.scan(ast).toSet()

// Remove all generic declarations
private fun removeAllGenerics(
    ast: Ast
) = ast.copy(declarations = ast.declarations.filter { root ->
    root.declaration.genericDeclaration.isEmpty()
})



// For each generic declaration and type parameter pair create the specialised instance
private fun createNewSpecializations(
    ast: Ast,
    candidates: Set<Pair<Namer, List<TypeRef>>>,
    baseId: Namer
): Pair<Ast, Map<Pair<Namer, List<TypeRef>>, Namer>> {
    val declarationLookup = ast.declarations.associateBy { it.declaration.id }

    val results = candidates.mapIndexed { index, key ->
        val prefixId = baseId + index
        val (sourceId, typeParams) = key
        val root = declarationLookup[sourceId]!!
        val genericTypeToRealLookup = root.declaration.genericDeclaration.zip(typeParams)
            .associate { (generic, target) -> (TypeRef.Generic(generic.name, generic.id) as TypeRef) to target }

        val updater = object: AbstractUpdater<Unit>(Unit, { _,_ -> Unit }) {

            override fun updateTypeRef(
                self: TypeRef,
                path: List<Any>
            ): Pair<TypeRef, Unit> {
                return super.updateTypeRef(self, path).mapFirst {
                    genericTypeToRealLookup.getOrDefault(it, it)
                }
            }

            override fun updateExpressionLambda(
                self: Expression.Lambda,
                path: List<Any>
            ): Pair<Expression, Unit> {
                return super.updateExpressionLambda(self, path).mapFirst { expr ->
                    // Later the transform LambdaToClass relies on this id being globally unique
                    // There are no global references using this id, so it should be safe to just re-write it
                    (expr as Expression.Lambda).copy(id = prefixId / expr.id)
                }
            }

            fun update(decl: Declaration): Declaration {
                return updateDeclaration(when (decl) {
                    is Declaration.Klass -> decl.copy(id = prefixId / decl.id, genericDeclaration = listOf())
                    is Declaration.Function -> decl.copy(id = prefixId / decl.id, genericDeclaration = listOf())
                    is Declaration.Let -> decl.copy(id = prefixId / decl.id, genericDeclaration = listOf())
                    is Declaration.Alias, is Declaration.Generic -> decl
                }, listOf()).first
            }
        }

        root.copy(declaration = updater.update(root.declaration)) to key
    }

    val roots = results.map { (xroot, xkey) -> xroot }
    val keys = results.associate { (xroot, xkey) -> xkey to xroot.declaration.id }
    return ast.copy(declarations = ast.declarations + roots) to keys
}



private fun loop(ast: Ast, specializations: Map<Pair<Namer, List<TypeRef>>, Namer>, iteration: Int): Ast {
    val candidates = findConcreteGenericReferences(ast) - specializations.keys
    return if (candidates.isEmpty()) {
        ast
    } else {
        val (newAst, newSpecs) = createNewSpecializations(ast, candidates, Namer("u")+iteration)
        val newSpecs2 = newSpecs + specializations
        val newAst2 = replaceConcreteGenericReferences(newAst, newSpecs2)
        loop(newAst2, newSpecs2, iteration+1)
    }
}

fun genericSpecialization(ast: Ast): Ast {
    val newAst = loop(ast, mapOf(), 0)
    val removed = removeAllGenerics(newAst)
    return removed
}
