package com.supersoftcafe.yafl.tointermediate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.codegen.*
import com.supersoftcafe.yafl.utils.*



private class Globals(val type: Map<Long, Declaration.Type>, val data: Map<Long, Declaration.Data>)

private fun localName(name: String, id: Long) = "v$$name$$id"
private fun globalName(name: String, id: Long) = "v$$name$$id"

private fun DataRef?.toCgValue(type: CgType, globals: Globals, namer: Namer): Either<Pair<List<CgOp>,CgValue>, List<String>> {
    return when (this) {
        null ->
            throw IllegalStateException("Dangling null DataRef")

        is DataRef.Unresolved ->
            Either.error(listOf("Dangling unresolved DataRef"))

        is DataRef.Local ->
            Either.some(Pair(listOf(), CgValue.Register(localName(name, id), type)))

        is DataRef.Global ->
            when (val data = globals.data[id]) {
                null ->
                    throw IllegalStateException("Missing declaration for given DataRef")

                is Declaration.Let -> {
                    val result = CgValue.Register(namer.toString(), type)
                    when (data.body) {
                        is Expression.Lambda ->
                            Either.some(Pair(listOf(CgOp.LoadStaticCallable(result, CgValue.UNIT, globalName(name, id))), result))

                        else ->
                            Either.some(Pair(listOf(CgOp.Load(result, CgValue.Global(globalName(name, id), CgTypePointer(type)))), result))
                    }
                }
            }
    }
}

private fun TypeRef?.toCgType(globals: Globals): Either<CgType, List<String>> {
    return when (this) {
        null ->
            throw IllegalStateException("Danging null TypeRef")

        is TypeRef.Unresolved ->
            Either.Error(listOf("Dangling unresolved TypeRef"))

        is TypeRef.Named -> {
            when (val d = globals.type[id]) {
                is Declaration.Alias -> {
                    throw IllegalStateException("Dangling alias")
                }

                is Declaration.Struct -> {
                    val fields =  d.parameters.map {
                        it.typeRef.toCgType(globals)
                    }
                    val values = fields.flatMap { when (it) {
                        is Either.Some -> listOf(it.value)
                        is Either.Error -> listOf()
                    } }
                    val errors = fields.flatMap { when (it) {
                        is Either.Some -> listOf()
                        is Either.Error -> it.error
                    } }
                    if (values.size == fields.size) {
                        Either.Some(CgTypeStruct(values))
                    } else {
                        Either.Error(errors)
                    }
                }

                null -> {
                    throw IllegalStateException("Type lookup failure")
                }
            }
        }

        is TypeRef.Tuple -> {
            val fields = fields.map {
                it.typeRef.toCgType(globals)
            }
            val values = fields.flatMap { when (it) {
                is Either.Some -> listOf(it.value)
                is Either.Error -> listOf()
            } }
            val errors = fields.flatMap { when (it) {
                is Either.Some -> listOf()
                is Either.Error -> it.error
            } }
            if (values.size == fields.size) {
                Either.Some(CgTypeStruct(values))
            } else {
                Either.Error(errors)
            }
        }

        is TypeRef.Callable -> {
            Either.Some(CgTypePrimitive.CALLABLE)
        }

        is TypeRef.Primitive -> {
            Either.Some(when (kind) {
                PrimitiveKind.Bool -> CgTypePrimitive.BOOL
                PrimitiveKind.Int8 -> CgTypePrimitive.INT8
                PrimitiveKind.Int16 -> CgTypePrimitive.INT16
                PrimitiveKind.Int32 -> CgTypePrimitive.INT32
                PrimitiveKind.Int64 -> CgTypePrimitive.INT64
                PrimitiveKind.Float32 -> CgTypePrimitive.FLOAT32
                PrimitiveKind.Float64 -> CgTypePrimitive.FLOAT64
            })
        }
    }
}

private fun CgValue.extractAll(namer: Namer): Pair<List<CgOp>, List<CgValue>> {
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

private fun Expression.toCgOps(namer: Namer, globals: Globals, locals: Map<Long,Declaration.Data>): Either<Pair<List<CgOp>, CgValue>, List<String>> {
    return when (this) {
        is Expression.Lambda ->
            throw IllegalStateException("No lambda should exist here")

        is Expression.Integer ->
            typeRef.toCgType(globals)
                .map { type -> Either.Some(Pair(listOf<CgOp>(), CgValue.Immediate(value.toString(), type))) }

        is Expression.Call ->
            Either.combine(
                typeRef.toCgType(globals),
                callable.toCgOps(namer + 1, globals, locals),
                parameter.toCgOps(namer + 2, globals, locals)
            ) { type, (cops, cresult), (pops, presult) ->
                val (eops, eresult) = presult.extractAll(namer + 3)
                val result = CgValue.Register(namer.plus(3).toString(), type)
                val op = CgOp.Call(result, cresult, eresult)
                Either.Some(Pair(cops + pops + eops + op, result))
            }

        is Expression.Tuple ->
            typeRef.toCgType(globals).map { type ->
                Either.some<List<TupleExpressionField>, List<String>>(fields)
                    .foldIndexed<TupleExpressionField, Pair<List<CgOp>, List<CgValue>>, List<String>>(
                        Pair(listOf(), listOf())
                    ) { index, (acc_ops, acc_value), field ->
                        field.expression.toCgOps(namer + (index * 3), globals, locals)
                            .map { (ops, value) ->
                                Either.Some(
                                    if (field.unpack) {
                                        val (extract_ops, extract_result) = value.extractAll(namer + (index * 3 + 1))
                                        Pair(acc_ops + ops + extract_ops, acc_value + extract_result)
                                    } else {
                                        Pair(acc_ops + ops, acc_value + value)
                                    }
                                )
                            }
                    }
                    .map { (ops, values) ->
                        Either.Some(values.foldIndexed(Pair(ops, CgValue.undef(type))) { index, (ops, acc), value ->
                            val op = CgOp.InsertValue(namer.plus(index * 3 + 2).toString(), acc, intArrayOf(index), value)
                            Pair(ops + op, op.result)
                        })
                    }
            }

        is Expression.BuiltinBinary ->
            Either.combine(
                typeRef.toCgType(globals),
                left.toCgOps(namer + 1, globals, locals),
                right.toCgOps(namer + 2, globals, locals)
            ) { type, (left_ops, left_result), (right_ops, right_result) ->
                val cgOp = when (op) {
                    BuiltinBinaryOp.ADD_I32, BuiltinBinaryOp.ADD_I64 -> CgBinaryOp.ADD
                    BuiltinBinaryOp.EQU_I32 -> CgBinaryOp.ICMP_EQ
                    BuiltinBinaryOp.MUL_I32 -> CgBinaryOp.MUL
                    BuiltinBinaryOp.SUB_I32 -> CgBinaryOp.SUB
                }

                val result = CgValue.Register(namer.plus(3).toString(), type)
                val op = CgOp.Binary(result, cgOp, left_result, right_result)
                Either.Some(Pair(left_ops + right_ops + op, result))
            }

        is Expression.LoadData ->
            // TODO: Loading something that is a function needs different handling
            typeRef.toCgType(globals)
                .map { type -> dataRef.toCgValue(type, globals, namer) }

        is Expression.If ->
            Either.combine(
                typeRef.toCgType(globals),
                ifTrue.toCgOps(namer + 1, globals, locals),
                ifFalse.toCgOps(namer + 2, globals, locals),
                condition.toCgOps(namer + 3, globals, locals)
            ) { type, (ifTrueOps, ifTrueResult), (ifFalseOps, ifFalseResult), (conditionOps, conditionResult) ->
                val ifTrueLabel = CgOp.Label(namer.plus(4).toString())
                val ifFalseLabel = CgOp.Label(namer.plus(5).toString())
                val endLabel = CgOp.Label(namer.plus(6).toString())
                val result = CgValue.Register(namer.plus(7).toString(), type)

                val ops = conditionOps +
                        CgOp.Branch(conditionResult, ifTrueLabel.name, ifFalseLabel.name) +
                        ifTrueLabel +
                        ifTrueOps +
                        CgOp.Jump(endLabel.name) +
                        ifFalseLabel +
                        ifFalseOps +
                        CgOp.Jump(endLabel.name) +
                        endLabel +
                        CgOp.Phi(result, listOf(Pair(ifTrueResult, ifTrueLabel.name), Pair(ifFalseResult, ifFalseLabel.name)))

                Either.Some(Pair(ops, result))
            }

        else ->
            TODO("Operation ${this.javaClass.canonicalName} not implemented")
    }
}


/* There should be no nested lambdas remaining, so all variable references are either
 * global, parameter or immediate local, with no nested functions.
 */
fun convertToIntermediate(ast: Ast): Either<List<CgThing>, List<String>> {
    // TODO: Locate the 'main' function. There must be only one, with no params and a single Int32 result.
    //    In below mapping, give that main function a well defined name

    val globals = Globals(
        ast.declarations.mapNotNull { it.declaration as? Declaration.Type }.associateBy { it.id },
        ast.declarations.mapNotNull { it.declaration as? Declaration.Data }.associateBy { it.id })

    val namer = Namer("r")
    val result = Either
        .some<List<Root>,List<String>>(ast.declarations)
        .mapIndexedNotNull<Root, Pair<CgThing, CgThingFunction?>, List<String>> { index, (imports, declaration) ->
            when (declaration) {
                is Declaration.Struct ->
                    Either.some(null)

                is Declaration.Alias ->
                    Either.some(null)

                is Declaration.Let ->
                    when (val body = declaration.body) {
                        is Expression.Lambda -> // Function
                            Either.combine(
                                body.body.typeRef.toCgType(globals),
                                body.body.toCgOps(namer + index, globals, body.parameters.associateBy { it.id }),
                                Either.some<List<Declaration.Let>,List<String>>(body.parameters)
                                    .mapIndexed { _, param ->
                                        param.typeRef.toCgType(globals)
                                            .map { paramType -> Either.Some(CgValue.Register(localName(param.name, param.id), paramType)) }
                                    }
                            ) { returnType, (ops, returnValue), params ->
                                Either.some(Pair<CgThing, CgThingFunction?>(CgThingFunction(
                                    globalName(declaration.name, declaration.id),
                                    returnType,
                                    listOf(CgValue.THIS) + params,
                                    listOf(),
                                    ops + CgOp.Return(returnValue)
                                ), null))
                            }

                        null ->
                            throw IllegalStateException("Empty let")

                        else -> // Variable and init function
                            Either.combine(
                                declaration.typeRef.toCgType(globals),
                                body.toCgOps(namer + index, globals, mapOf())
                            ) { type, (ops, result) ->
                                val name = globalName(declaration.name, declaration.id)
                                Either.some(
                                    Pair<CgThing, CgThingFunction?>(
                                        CgThingVariable(name, type),
                                        CgThingFunction(
                                            "init\$$name",
                                            type,
                                            listOf(CgValue.THIS),
                                            listOf(),
                                            ops + CgOp.Return(result)
                                        )
                                    )
                                )
                            }
                    }
            }
        }
        .map { things ->
            // Create main function and append it
            val userMainList = globals.data.values
                .filterIsInstance<Declaration.Let>()
                .filter {
                    val lambda = it.body as? Expression.Lambda
                    val result = lambda != null && it.name.endsWith("::main") && lambda.parameters.isEmpty() && lambda.body.typeRef == TypeRef.Primitive(PrimitiveKind.Int32)
                    result
                }
            val userMain = userMainList.firstOrNull()

            if (userMain == null) {
                Either.error(listOf("No main function found"))
            } else if (userMainList.size > 1) {
                Either.error(listOf("Too many user main functions found"))
            } else {
                val globalVars = things.mapNotNull { (thing, initFunc) ->
                    if (thing is CgThingVariable && initFunc != null) {
                        Pair(thing, initFunc)
                    } else {
                        null
                    }
                }

                val initNamer = Namer("i")
                val initOps = globalVars.flatMapIndexed { index, (thing, initFunc) ->
                    val namerBase = initNamer + index

                    val methodReg = CgValue.Register(namerBase.plus(0).toString(), CgTypePrimitive.CALLABLE)
                    val resultReg = CgValue.Register(namerBase.plus(1).toString(), thing.type)
                    listOf(
                        CgOp.LoadStaticCallable(methodReg, CgValue.NULL, initFunc.name),
                        CgOp.Call(resultReg, methodReg, listOf()),
                        CgOp.Store(thing.type, CgValue.Global(thing.name, thing.type), resultReg)
                    )
                }

                val mainNamer = initNamer + globalVars.size
                val mainMethodReg = CgValue.Register(mainNamer.plus(0).toString(), CgTypePrimitive.CALLABLE)
                val mainResultReg = CgValue.Register(mainNamer.plus(1).toString(), CgTypePrimitive.INT32)
                val retOps = listOf(
                    CgOp.LoadStaticCallable(mainMethodReg, CgValue.NULL, globalName(userMain.name, userMain.id)),
                    CgOp.Call(mainResultReg, mainMethodReg, listOf()),
                    CgOp.Return(mainResultReg)
                )

                val main = CgThingFunction(
                    "synth_main",
                    CgTypePrimitive.INT32,
                    listOf(CgValue.THIS),
                    listOf(),
                    initOps + retOps
                )

                // Flatten the list and append main function
                Either.some(things.map { it.first } + globalVars.map { it.second } + (main as CgThing))
            }
        }

    return result
}