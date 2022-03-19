package yafl.ast






private fun AstProject.mapDeclaration(
    doFun: (Declaration.Fun) -> Declaration.Fun = { it },
    doStruct: (Declaration.Struct) -> Declaration.Struct = { it }
) = AstProject(modules.mapValues { entry -> entry.value.map { declaration ->
    when (declaration) {
        is Declaration.Fun -> doFun(declaration)
        is Declaration.Struct -> doStruct(declaration)
        else -> throw IllegalArgumentException()
    }
}})

private fun AstProject.resolveToFullyQualifiedNames() = mapDeclaration(
    // Where type is specified, we should be able to resolve it
    // Vague named referenced need to be converted to invoke local or invoke remote etc
    doFun = { fn -> fn.copy(
        params = t,
        type = t,
        declarations = t,
        expression = t
    ) }
)



private fun AstProject.resolveUnknownTypes(): AstProject {
    throw IllegalArgumentException()
}



fun compileAst(project: AstProject): AstProject {
    return project
        .resolveToFullyQualifiedNames()
        // .resolveUnknownTypes()
}

