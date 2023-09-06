package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.*
import com.supersoftcafe.yafl.models.llir.*
import com.supersoftcafe.yafl.passes.p5_generate.*
import com.supersoftcafe.yafl.utils.*



class Globals(
    val type: Map<Namer, Declaration.Type>,
    val data: Map<Namer, Declaration.Data>,
) {
    val enumInfo: Map<Namer, Lazy<EnumRuntimeInfo>> = type.values
        .filterIsInstance<Declaration.Enum>()
        .associate { it.id to lazy { createEnumInfo(it, this) } }
}


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



fun CgValue.extractAll(namer: Namer): Pair<List<CgOp>, List<CgValue>> {
    return when (val type = type) {
        is CgTypeStruct -> {
            val ops = type.fields.mapIndexed { index, field ->
                CgOp.ExtractValue(namer.plus(index).toString(), this, intArrayOf(index))
            }
            val values = ops.map { it.result }
            Pair(ops, values)
        }
        else ->
            Pair(listOf(), listOf(this))
    }
}

fun Declaration.Klass.findMember(id: Namer, globals: Globals): Declaration.Data? {
    return parameters.firstOrNull { it.id == id }
        ?: members.firstOrNull { it.id == id }
        ?: extends.firstNotNullOfOrNull {
            (globals.type[(it as TypeRef.Klass).id] as Declaration.Klass).findMember(id, globals)
        }
}

/* There should be no nested lambdas remaining, so all variable references are either
 * global, parameter or immediate local, with no nested functions.
 */
fun convertToIntermediate(ast: Ast): List<CgThing> {
    val globals = Globals(
        ast.declarations.flatMap { it.declarations.filterIsInstance<Declaration.Type>() }.associateBy { it.id },
        ast.declarations.flatMap { it.declarations.filterIsInstance<Declaration.Data>() }.associateBy { it.id })

    val namer = Namer("r")
    val things = (globals.type.values + globals.data.values).flatMapIndexed { index, declaration ->
        val namer = namer + index

        when (declaration) {
            is Declaration.Enum ->
                declaration.enumToIntermediate(namer, globals)

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

    val functions = things.filterIsInstance<CgThingFunction>().associateBy { it.globalName }
    val variables = things.filterIsInstance<CgThingVariable>().associateBy { it.name }

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

    if (userMain == null) {
        throw IllegalStateException("No main function found")
    } else if (userMainList.size > 1) {
        throw IllegalStateException("Too many user main functions found")
    }

    val globalVars = functions.filterKeys { it.startsWith("init\$") }.map { (_, initFunc) ->
        Pair(variables[initFunc.globalName.drop(5)]!!, initFunc)
    }

    val initNamer = Namer("i")
    val initOps = globalVars.flatMapIndexed { index, (thing, initFunc) ->
        val namerBase = initNamer + index

        val methodReg = CgValue.Register(namerBase.plus(0).toString(), CgTypeStruct.functionPointer)
        val resultReg = CgValue.Register(namerBase.plus(1).toString(), thing.type)
        listOf(
            CgOp.CallStatic(resultReg, CgValue.UNIT, initFunc.globalName, listOf()),
            CgOp.Store(thing.type, CgValue.Global(thing.name, thing.type), resultReg)
        )
    }

    val mainNamer = initNamer + globalVars.size
    val mainMethodReg = CgValue.Register(mainNamer.plus(0).toString(), CgTypeStruct.functionPointer)
    val mainResultReg = CgValue.Register(mainNamer.plus(1).toString(), CgTypePrimitive.INT32)
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