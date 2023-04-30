package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.Ast
import com.supersoftcafe.yafl.ast.Declaration
import com.supersoftcafe.yafl.ast.TypeRef
import com.supersoftcafe.yafl.utils.Namer


private class GenericCallSiteReplacer(
    // Each use of a declaration (data or type) with given concrete type parameters must have a specialised
    // form that is the target of the map. If null, it is pending generation, otherwise already done so don't
    // re-do. Specialization happens over three phases:
    //  1. Discovery: Find uses of generic declarations that have concrete type parameters
    //  2. Specialization: Create specializations of each generic declaration with the discovered type parameters
    //  3. Re-write call sites: Uses of these generics must be replaced with uses of the specialised forms
    // These phases can occur out of order, so long as they iterate until there is no more to do.
    // Finally, remove original generic declarations, when re-writing is done.

    val targets: Map<Pair<Namer, List<TypeRef>>, Namer>
) : AbstractUpdater<List<Unit>>(emptyList(), { l, r -> l+r }) {

    // Replace all uses of specialized generic declarations with references to their specialized counterparts
}

private class GenericScanner : AbstractScanner<Pair<Namer, List<TypeRef>>>() {
    // Find all concrete uses of generic declarations where the type parameters are well defined
}

private fun removeAllGenerics(ast: Ast): Ast {
    // Remove all generic declarations
}

private fun createNewSpecializations(ast: Ast, candidates: Set<Pair<Namer, List<TypeRef>>>): Pair<Ast, Map<Pair<Namer, List<TypeRef>>, Namer>> {
    // For each generic declaration and type parameter pair create the specialised instance
}

private fun loop(ast: Ast, specializations: Map<Pair<Namer, List<TypeRef>>, Namer>): Ast {
    val candidates = GenericScanner().scan(ast).toSet() - specializations.keys
    return if (candidates.isEmpty()) {
        ast
    } else {
        val (newAst, newSpecs) = createNewSpecializations(ast, candidates)
        val newSpecs2 = newSpecs + specializations
        val newAst2 = GenericCallSiteReplacer(newSpecs2).update(newAst).first
        loop(newAst2, newSpecs2)
    }
}

fun genericSpecialization(ast: Ast): Ast {
    val newAst = loop(ast, mapOf())
    val removed = removeAllGenerics(newAst)
    return removed
}
