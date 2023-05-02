package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Namer

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
    val stringToDataRef: Map<String, DataRef.Resolved>,
    val globalIdToDataRef: Map<Namer, DataRef.Resolved>
) {
    private fun Expression.Tuple.replaceStrings() = copy(
        fields = fields.map {
            it.copy(
                expression = it.expression.replaceStrings()
            )
        }
    )

    private fun Expression.replaceStrings(): Expression = when (this) {
        is Expression.Float -> this
        is Expression.Integer -> this

        is Expression.Characters ->
            Expression.LoadData(
                sourceRef,
                stringType,
                stringToDataRef[value]!!)

        is Expression.LoadData ->
            if (dataRef is DataRef.Resolved && dataRef.id in globalIdToDataRef) {
                copy(dataRef = globalIdToDataRef[dataRef.id]!!)
            } else {
                this
            }

        is Expression.RawPointer -> copy(field = field.replaceStrings())
        is Expression.Let -> copy(let = let.replaceStrings(), tail = tail.replaceStrings())
        is Expression.ArrayLookup -> copy(array = array.replaceStrings(), index = index.replaceStrings())
        is Expression.Assert -> copy(value = value.replaceStrings(), condition = condition.replaceStrings())
        is Expression.Call -> copy(callable = callable.replaceStrings(), parameter = parameter.replaceStrings())
        is Expression.Parallel -> copy(parameter = parameter.replaceStrings())
        is Expression.If -> copy(condition = condition.replaceStrings(), ifTrue = ifTrue.replaceStrings(), ifFalse = ifFalse.replaceStrings())
        is Expression.Lambda -> copy(body = body.replaceStrings(), parameters = parameters.map { it.replaceStrings() })
        is Expression.Llvmir -> copy(inputs = inputs.map { it.replaceStrings() })
        is Expression.LoadMember -> copy(base = base.replaceStrings())
        is Expression.NewKlass -> copy(parameter = parameter.replaceStrings())
        is Expression.Tuple -> replaceStrings()
    }

    private fun Declaration.Let.replaceStrings() = copy(
        dynamicArraySize = dynamicArraySize?.replaceStrings(),
        body = body?.replaceStrings(),
    )

    private fun Declaration.Function.replaceStrings() = copy(
        thisDeclaration = thisDeclaration.replaceStrings(),
        parameters = parameters.map { it.replaceStrings() },
        body = body?.replaceStrings(),
    )

    private fun Declaration.Klass.replaceStrings() = copy(
        parameters = parameters.map { it.replaceStrings() },
        members = members.map { it.replaceStrings() },
    )

    private fun Declaration.Generic.replaceStrings() = this

    fun replaceStrings(declaration: Declaration) = when (declaration) {
        is Declaration.Let -> declaration.replaceStrings()
        is Declaration.Function -> declaration.replaceStrings()
        is Declaration.Alias -> declaration
        is Declaration.Klass -> declaration.replaceStrings()
        is Declaration.Generic -> declaration.replaceStrings()
    }
}

fun stringsToGlobals(ast: Ast): Ast {
    val allStrings = StringScanner().scan(ast).toSet()

    // Find the string class in the ast. We need to reference it in the string literal declarations.
    val stringDeclaration = ast.declarations.mapNotNull {
        it.declaration as? Declaration.Klass
    } .first {
        it.name == "System::String"
    }
    val stringType = TypeRef.Klass(
        name = stringDeclaration.name,
        id = stringDeclaration.id,
        extends = stringDeclaration.extends.filterIsInstance<TypeRef.Klass>(),
        genericParameters = listOf()
    )

    // Match anything that is declaration of an immediate string literal
    fun declarationToStringMatcher(root: Root): Boolean {
        val declaration = root.declaration
        return declaration is Declaration.Let
                && declaration.body is Expression.Characters
                && declaration.body.value in allStrings
    }

    val namer = Namer("string_")
    val globalsToReplace = ast.declarations.filter(::declarationToStringMatcher).map { it.declaration }

    val newStringGlobals = allStrings.mapIndexed { index, string ->
        val id = namer + index
        val name = "\$globals::strings::$id"
        string to Declaration.Let(
            sourceRef = SourceRef.EMPTY,
            name = name,
            id = id,
            scope = Scope.Global,
            typeRef = stringType,
            sourceTypeRef = stringType,
            body = Expression.Characters(SourceRef.EMPTY, stringType, string),
            signature = stringType.toSignature(name),
            genericDeclaration = listOf()
        )
    }
    val stringToDataRef = newStringGlobals.associate { (string, declaration) ->
        string to DataRef.Resolved(
            declaration.name,
            declaration.id,
            declaration.scope,
        )
    }
    val globalIdToDataRef = globalsToReplace.associate { declaration ->
        declaration.id to stringToDataRef[((declaration as Declaration.Let).body as Expression.Characters).value]!!
    }

    val stringReplacer = StringReplacer(stringType, stringToDataRef, globalIdToDataRef)
    return ast.copy(declarations =
            ast.declarations
                .filterNot(::declarationToStringMatcher)
                .map { it.copy(declaration = stringReplacer.replaceStrings(it.declaration)) } +
            newStringGlobals.map { (_,d) -> Root(importsOf(), d, "") }
    )
}
