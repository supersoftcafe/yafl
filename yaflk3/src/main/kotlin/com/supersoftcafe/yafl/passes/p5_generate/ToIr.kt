package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.*
import com.supersoftcafe.yafl.models.llir.*
import com.supersoftcafe.yafl.passes.p5_generate.*
import com.supersoftcafe.yafl.utils.*



class Globals(
    val type: Map<Namer, Declaration.Type>,
    val data: Map<Namer, Declaration.Data>,
)


fun DataRef?.toCgValue(
    type: CgType,
    globals: Globals,
    locals: Map<Namer, Pair<Declaration.Data, CgValue>>, namer: Namer
): Pair<List<CgOp>, CgValue> {
    return when (this) {
        null ->
            throw IllegalStateException("Dangling null DataRef")

        is DataRef.Unresolved ->
            throw IllegalStateException("Dangling unresolved DataRef")

        is DataRef.Resolved -> {
            when (scope) {
                is Scope.Member ->
                    throw IllegalStateException("Dangling member scope")

                Scope.Local -> {
                    val (_, value) = locals[id]!!
                    Pair(listOf(), value)
                }

                Scope.Global ->
                    when (val data = globals.data[id]) {
                        null ->
                            throw IllegalStateException("Missing declaration for given DataRef")

                        is Declaration.Let -> {
                            val result = CgValue.Register(namer.toString(), type)
                            Pair(listOf(CgOp.Load(result, CgValue.Global(data.globalDataName(), CgTypePointer(type)))), result)
                        }

                        is Declaration.Function -> {
                            val result = CgValue.Register(namer.toString(), type)
                            Pair(listOf(CgOp.LoadStaticCallable(result, CgValue.UNIT, data.globalDataName())), result)
                        }
                    }
            }
        }
    }
}



fun Declaration.Klass.findMember(id: Namer, globals: Globals): Declaration.Data? {
    return parameters.firstOrNull { it.id == id }
        ?: members.firstOrNull { it.id == id }
        ?: extends.firstNotNullOfOrNull {
            (globals.type[(it as TypeRef.Klass).id] as Declaration.Klass).findMember(id, globals)
        }
}

private fun getDeclarationInitPriority(d: Declaration) = when (d) {
    is Declaration.Let ->
        // Simple literals come first. This is hacky, and will have issues, so must fix in the future.
        // TODO: mix static dependency analysis and lazy init to correctly init globals.
        when (d.body) {
            is Expression.Characters -> 0
            is Expression.Integer -> 0
            is Expression.Float -> 0
            else -> 1
        }
    else -> 2
}

/* There should be no nested lambdas remaining, so all variable references are either
 * global, parameter or immediate local, with no nested functions.
 */
fun convertToIntermediate(ast: Ast): List<CgThing> {
    val allDeclarationsAtTopLevel = ast.declarations.flatMap { it.declarations }
    val globals = Globals(
        allDeclarationsAtTopLevel.filterIsInstance<Declaration.Type>().associateBy { it.id },
        allDeclarationsAtTopLevel.filterIsInstance<Declaration.Data>().flatMap {
            // Extract the destructured globals
            if (it is Declaration.Let) it.flatten() else listOf(it)
        }.associateBy { it.id })

    val namer = Namer("r")
    val things = allDeclarationsAtTopLevel
        .sortedBy(::getDeclarationInitPriority)
        .flatMapIndexed { index, declaration ->
            val namer = namer + index

            when (declaration) {
                is Declaration.Klass ->
                    declaration.klassToIntermediate(namer, globals)

                is Declaration.Let ->
                    declaration.letToIntermediate(namer, globals)

                is Declaration.Function ->
                    declaration.functionToIntermediate(namer, globals)

                is Declaration.Alias ->
                    listOf()
            }
        }

    // Create main function and append it
    val userMainList = globals.data.values
        .filterIsInstance<Declaration.Function>()
        .filter {
            if (it.name == "main" || it.name.endsWith("::main")) {
                it.parameter.isEmpty() && it.body?.typeRef == TypeRef.Primitive(PrimitiveKind.Int32)
            } else {
                false
            }
        }
    val userMain = userMainList.firstOrNull()

    if (userMain == null)
        throw IllegalStateException("No main function found")
    else if (userMainList.size > 1)
        throw IllegalStateException("Too many user main functions found")

    val initOps = things.mapNotNull { thing ->
        if (thing is CgThingFunction && thing.globalName.startsWith("init\$"))
             CgOp.CallStatic(CgValue.VOID, CgValue.UNIT, thing.globalName, listOf())
        else null
    }

    val mainResultReg = CgValue.Register("main_result", CgTypePrimitive.INT32)
    val retOps = listOf(
        CgOp.CallStatic(mainResultReg, CgValue.UNIT, userMain.globalDataName(), listOf()),
        CgOp.Return(mainResultReg)
    )

    val main = CgThingFunction(
        "synth_main",
        "",
        CgTypePrimitive.INT32,
        listOf(CgValue.THIS),
        initOps + retOps
    )

    // Return everything and the synthetic main function
    return things + (main as CgThing)
}