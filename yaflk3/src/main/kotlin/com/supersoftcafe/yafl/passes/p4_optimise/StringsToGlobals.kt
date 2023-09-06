package com.supersoftcafe.yafl.passes.p4_optimise

import com.supersoftcafe.yafl.models.ast.*
import com.supersoftcafe.yafl.passes.AbstractScanner
import com.supersoftcafe.yafl.passes.AbstractUpdater
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.tupleOf

private class StringScanner : AbstractScanner<String>() {
    override fun scan(self: Expression?, parent: Expression?): List<String> {
        return when (self) {
            is Expression.Characters -> listOf(self.value)
            else -> super.scan(self, parent)
        }
    }
}

private class StringReplacer(
    val stringType: TypeRef.Klass,
    val stringToDataRef: Map<String, DataRef.Resolved>
) : AbstractUpdater<String>("", { x,y -> x + y}) {
    override fun updateExpressionCharacters(
        self: Expression.Characters,
        path: List<Any>
    ): Pair<Expression, String> {
        return tupleOf(Expression.LoadData(self.sourceRef, stringType, stringToDataRef[self.value]!!), "")
    }
}

fun stringsToGlobals(ast: Ast): Ast {
    val allStrings = StringScanner().scan(ast).toSet()

    // Find the string class in the ast. We need to reference it in the string literal declarations.
    val stringDeclaration = ast.declarations.flatMap { root ->
        root.declarations.filterIsInstance<Declaration.Klass>()
    } .first {
        it.name == "System::String"
    }
    val stringType = TypeRef.Klass(
        id = stringDeclaration.id,
        name = stringDeclaration.name,
        extends = stringDeclaration.extends.filterIsInstance<TypeRef.Klass>()
    )

    // Create global declaration for each unique string
    val namer = Namer("string_")
    val newStringGlobals = allStrings.mapIndexed { index, string ->
        val id = namer + index
        val name = "\$globals::strings::$id"
        string to Declaration.Let(
            sourceRef = SourceRef.EMPTY,
            name = name, id = id,
            scope = Scope.Global,
            typeRef = stringType,
            sourceTypeRef = stringType,
            body = Expression.Characters(SourceRef.EMPTY, stringType, string),
            signature = stringType.toSignature(name)
        )
    }
    val stringToDataRef = newStringGlobals.associate { (string, declaration) ->
        string to DataRef.Resolved(
            declaration.name,
            declaration.id,
            declaration.scope,
        )
    }

    // Replace all the string literals with globals
    val (ast2, _) = StringReplacer(stringType, stringToDataRef).update(ast)
    return ast2.copy(declarations = ast2.declarations + Root(importsOf(), newStringGlobals.map { (_,d) -> d }, "") )
}
