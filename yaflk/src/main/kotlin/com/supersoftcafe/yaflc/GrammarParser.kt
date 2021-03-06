package com.supersoftcafe.yaflc

import kotlinx.collections.immutable.PersistentList
import kotlinx.collections.immutable.persistentListOf


class GrammarParser(val ast: Ast) {
    fun parseDottyName(tk: Tokens): Result<PersistentList<String>> {
        val result = tk.AllOf(TokenKind.NAME) { ListOfWhile(TokenKind.DOT, TokenKind.NAME) }
            .map { _, value -> persistentListOf(value.v1.text).addAll(value.v2.map { it.text }) }
        return result
    }

    fun parseModuleAndName(tk: Tokens): Result<String> {
        val result = tk.AllOf({ FailIsAbsent(TokenKind.MODULE) }, ::parseDottyName).map { _, (_, b) -> b.joinToString(".") }
        return result
    }

    fun parseImport(tk: Tokens): Result<Module> {
        val result = tk.AllOf({ FailIsAbsent(TokenKind.USE) }, ::parseDottyName)
            .map { _, (_, b) -> ast.findOrCreateModule(b.joinToString(".")) }
        return result
    }

    fun parseImports(tk: Tokens): Result<PersistentList<Module>> {
        val result = tk.Repeat(::parseImport)
        return result
    }

    fun parseTypeNamed(tk: Tokens): Result<Type.Named> {
        val result = parseDottyName(tk).map { sourceRef, value ->
            Type.Named(value.last(), sourceRef, value.dropLast(1).reduceOrNull(String::plus))
        }
        return result
    }

    fun parseTypeTuple(tk: Tokens): Result<Type.Tuple> {
        val result = tk.Parameters(
            TokenKind.OBRACKET,
            { OneOf(
                { AllOf(TokenKind.NAME, TokenKind.COLON, ::parseType).map { sourceRef, (name, _, type) ->
                    tupleOf(name.text, type, sourceRef)
                } },
                { parseType(this@OneOf).map { sourceRef, type ->
                    tupleOf(null, type, sourceRef)
                } } ) },
            TokenKind.COMMA,
            TokenKind.CBRACKET)
            .map { sourceRef, value -> Type.Tuple(value.mapIndexed { index, (name, type, sourceRef2) ->
                Field(name ?: "v${index+1}", type, sourceRef2)
            }, sourceRef) }
        return result
    }

    fun parseTypeFunction(tk: Tokens): Result<Type.Function> {
        val result = tk.AllOf(::parseTypeTuple) { If(TokenKind.COLON, ::parseType) }
            .map { sourceRef, (parameters, result) ->
                Type.Function(parameters, result, sourceRef)
            }
        return result
    }

    fun parseType(tk: Tokens): Result<Type> {
        val result = tk.OneOf(::parseTypeFunction, ::parseTypeTuple, ::parseTypeNamed)
        return result
    }

    fun parseCallParameters(tk: Tokens): Result<List<Expression>> {
        val result = tk.Parameters(
            TokenKind.OBRACKET,
            ::parseExpression,
            TokenKind.COMMA,
            TokenKind.CBRACKET)
        return result
    }



    fun parseNamed(tk: Tokens): Result<Expression.LoadVariable> {
        val result = TokenKind.NAME(tk)
            .map { sourceRef, name -> Expression.LoadVariable(name.text, sourceRef = sourceRef) }
        return result
    }

    fun parseFloat(tk: Tokens): Result<Expression.LiteralFloat> {
        val result = TokenKind.FLOAT(tk).map { sourceRef, value ->
            Expression.LiteralFloat(
                value.text.toDouble(),
                sourceRef,
                if (value.text.endsWith("f4"))
                    ast.typeFloat32
                else
                    ast.typeFloat64
            )
        }
        return result
    }

    fun parseInteger(tk: Tokens): Result<Expression.LiteralInteger> {
        val result = TokenKind.INTEGER(tk).mapResult { token ->
            val t1 = token.value.text
            val (bits, t2) = when (val index = t1.indexOf('i')) {
                -1 -> tupleOf(32, t1)
                else -> tupleOf(t1.substring(index+1).toInt(), t1.substring(0, index))
            }
            val (radix, t3) = when {
                t2.startsWith("0b") -> tupleOf(2, t2.drop(2))
                t2.startsWith("0o") -> tupleOf(8, t2.drop(2))
                t2.startsWith("0d") -> tupleOf(10, t2.drop(2))
                t2.startsWith("0x") -> tupleOf(16, t2.drop(2))
                else -> tupleOf(10, t2)
            }

            val type = when (bits) {
                8 -> ast.typeInt8
                16 -> ast.typeInt16
                32 -> ast.typeInt32
                64 -> ast.typeInt64
                else -> null
            }

            if (type == null) {
                Result.Fail(token.sourceRef, "Invalid integer size")
            } else {
                val bigInt = t3.toBigInteger(radix)
                if (bigInt.bitLength() > (if (radix == 10) bits - 1 else bits))
                    Result.Fail(token.sourceRef, "Integer out of range")
                else
                    Result.Ok(Expression.LiteralInteger(bigInt.toLong(), token.sourceRef, type), token.sourceRef, token.tokens)
            }
        }
        return result
    }

    fun parseBuiltin(tk: Tokens): Result<Expression.Builtin> {
        val result = tk.AllOf(
            { FailIsAbsent(TokenKind.BUILTIN) },
            TokenKind.NAME,
            ::parseTupleExpr
        ).map { sourceRef, (_, name, params) ->
            val op = ast.builtinOps[name.text]
            val type = op?.result
            Expression.Builtin(name.text, op, params, sourceRef, type)
        }
        return result
    }

    fun parseTupleExpr(tk: Tokens): Result<Expression.Tuple> {
        val result = tk.Parameters(
            { FailIsAbsent(TokenKind.OBRACKET) },
            { OneOf(
                { AllOf(TokenKind.NAME, TokenKind.EQ, ::parseExpression).map { _, (name, _, expr) -> TupleField(name.text, expr, null, false) } },
                { AllOf(TokenKind.MUL, ::parseExpression ).map { _, (_, expr) -> TupleField(null, expr, null, true) }  },
                { parseExpression(this).map { _, expr -> TupleField(null, expr, null, false) } },
            )},
            TokenKind.COMMA,
            TokenKind.CBRACKET).map { sourceRef, fields ->
            Expression.Tuple(fields, sourceRef)
        }
        return result
    }

    fun parseCallExpr(tk: Tokens, nextLevel: Int): Result<Expression> {
        val result = when (val target = parseExpression(tk, nextLevel)) {
            is Result.Ok -> {
                when (val tuples = target.tokens.Repeat(::parseTupleExpr)) {
                    is Result.Ok ->
                        if (tuples.value.isEmpty()) {
                            target
                        } else {
                            Result.Ok(tuples.value.fold(target.value) { l, r ->
                                Expression.Call(l, r, r.sourceRef)
                            } as Expression.Call, target.sourceRef, tuples.tokens)
                        }
                    is Result.Fail -> target
                    is Result.Absent -> target
                }
            }
            is Result.Fail -> target.xfer()
            is Result.Absent -> target.xfer()
        }
        return result
    }

    fun parseUnaryExpr(tk: Tokens, nextLevel: Int, vararg operations: Pair<String,TokenKind>): Result<Expression> {
        val result = tk.AllOf(
            { TokenIs(operations.map { it.second }) },
            { parseExpression(this, nextLevel) }).map { sourceRef, (op, expr) ->
            val opName = operations.first { it.second == op.kind }.first
            val load = Expression.LoadVariable(opName, sourceRef = sourceRef)
            val param = Expression.Tuple(listOf(TupleField(null, expr, null, false)), expr.sourceRef)
            val call = Expression.Call(load, param, sourceRef = sourceRef + expr.sourceRef)
            call
        }

        if (result !is Result.Ok)
            return parseExpression(tk, nextLevel)

        return result
    }

    fun parseBinaryExpr(tk: Tokens, nextLevel: Int, vararg operations: Pair<String,TokenKind>): Result<Expression> {
        val leftResult = parseExpression(tk, nextLevel)
        if (leftResult !is Result.Ok)
            return leftResult
        val left = leftResult.value

        val result = leftResult.tokens.AllOf(
            { TokenIs(operations.map { it.second }) },
            { parseExpression(this, nextLevel) }).map { sourceRef, (op, right) ->
            val opName = operations.first { it.second == op.kind }.first
            val load = Expression.LoadVariable(opName, sourceRef = sourceRef)
            val param = Expression.Tuple(listOf(TupleField(null, left, null, false), TupleField(null, right, null, false)), left.sourceRef + right.sourceRef)
            val call = Expression.Call(load, param, left.sourceRef + right.sourceRef)
            call
        }

        if (result !is Result.Ok)
            return leftResult

        return result
    }

    fun parseTernaryExpr(tk: Tokens, nextLevel: Int): Result<Expression> {
        val conditionResult = parseExpression(tk, nextLevel)
        if (conditionResult !is Result.Ok)
            return conditionResult
        val condition = conditionResult.value

        val result = conditionResult.tokens.AllOf(
            TokenKind.QUESTION,
            { parseExpression(this, nextLevel) },
            TokenKind.COLON,
            { parseExpression(this, nextLevel) }
        ).map { sourceRef, (_, ifTrue, _, ifFalse) ->
            val cond = Expression.Condition(condition, ifTrue, ifFalse, condition.sourceRef + ifFalse.sourceRef)
            cond
        }

        if (result !is Result.Ok)
            return conditionResult

        return result
    }

    fun parseDeclarationsExpr(tk: Tokens, nextLevel: Int): Result<Expression> {
        val result = when (val locals = parseLocalDeclarations(tk)) {
            is Result.Absent -> parseExpression(tk, nextLevel)
            is Result.Fail -> locals.xfer()
            is Result.Ok ->
                if (locals.value.isEmpty()) {
                    parseExpression(tk, nextLevel)
                } else when (val next = parseExpression(locals.tokens, nextLevel)) {
                    is Result.Ok -> Result.Ok(Expression.DeclareLocal(locals.value, next.value, locals.sourceRef + next.sourceRef), locals.sourceRef + next.sourceRef, next.tokens)
                    is Result.Absent -> Result.Fail(locals.sourceRef, "Missing expression")
                    is Result.Fail -> next.xfer()
                }
        }
        return result
    }

    fun parseApplyExpr(tk: Tokens, nextLevel: Int): Result<Expression> {
        val leftResult = parseExpression(tk, nextLevel)
        if (leftResult !is Result.Ok)
            return leftResult
        val left = leftResult.value

        val result = leftResult.tokens.AllOf(
            TokenKind.APPLY,
            { parseExpression(this, nextLevel) }
        ).map { _, (_, right) -> Expression.Apply(left, right, left.sourceRef + right.sourceRef) }

        if (result !is Result.Ok)
            return leftResult

        return result
    }

    fun parseDotExpr(tk: Tokens, nextLevel: Int): Result<Expression> {
        val result = tk.AllOf(
            { parseExpression(this, nextLevel) },
            { ListOfWhile(TokenKind.DOT, TokenKind.NAME) }
        ).map { sourceRef, (base, names) ->
            names.fold(base) { expr, name ->
                Expression.LoadField(expr, name.text, null, sourceRef)
            }
        }
        return result
    }


    fun parseExpression(tk: Tokens, level: Int = 0): Result<Expression> {
        val result = when (level) {
            0 -> parseDeclarationsExpr(tk, level + 1)
            1 -> parseTernaryExpr(tk, level + 1)
            2 -> parseBinaryExpr(tk, level + 1, "`|`"  to TokenKind.OR)
            3 -> parseBinaryExpr(tk, level + 1, "`^`"  to TokenKind.XOR)
            4 -> parseBinaryExpr(tk, level + 1, "`&`"  to TokenKind.AND)
            5 -> parseBinaryExpr(tk, level + 1, "`=`"  to TokenKind.EQ, "`!=`"  to TokenKind.NEQ)
            6 -> parseBinaryExpr(tk, level + 1, "`<`"  to TokenKind.LT, "`<=`"  to TokenKind.LTE , "`>=`"  to TokenKind.GTE, "`>`" to TokenKind.GT)
            7 -> parseBinaryExpr(tk, level + 1, "`<<`" to TokenKind.SHL, "`>>`" to TokenKind.ASHR, "`>>>`" to TokenKind.LSHR)
            8 -> parseBinaryExpr(tk, level + 1, "`+`"  to TokenKind.ADD, "`-`"  to TokenKind.SUB)
            9 -> parseBinaryExpr(tk, level + 1, "`*`"  to TokenKind.MUL, "`/`"  to TokenKind.DIV , "`%`"   to TokenKind.REM)
            10 -> parseUnaryExpr(tk, level + 1, "`+`"  to TokenKind.ADD, "`-`"  to TokenKind.SUB , "`!`"   to TokenKind.NOT)
            11 -> parseApplyExpr(tk, level + 1)
            12 -> parseDotExpr  (tk, level + 1)
            13 -> parseCallExpr (tk, level + 1)
            else -> tk.OneOf(::parseInteger, ::parseFloat, ::parseBuiltin, ::parseNamed, ::parseTupleExpr)
        }
        return result
    }

    fun parseFunParams(tk: Tokens): Result<PersistentList<Declaration.Variable>> {
        val result = tk.Parameters(
            TokenKind.OBRACKET,
            { AllOf(
                    TokenKind.NAME,
                    { If(TokenKind.COLON, ::parseType) },
                    { If(TokenKind.EQ, ::parseExpression) }
                ).map { sourceRef, (name, type, body) ->
                    Declaration.Variable(name.text, body ?. let { ExpressionRef(it, type) }, type, sourceRef)
                }
            },
            TokenKind.COMMA,
            TokenKind.CBRACKET
        )
        return result
    }

    fun parseFun(tk: Tokens): Result<List<Declaration.Function>> {
        val result = tk.AllOf(
            { FailIsAbsent(TokenKind.FUN) },
            TokenKind.NAME,
            ::parseFunParams,
            { If(TokenKind.COLON, ::parseType) },
            { If(TokenKind.EQ, ::parseExpression) }
        ).map { sourceRef, (_, name, parameters, result, body) ->
            listOf(Declaration.Function(name.text, parameters, result, body?.let { ExpressionRef(it, result) }, null, sourceRef))
        }
        return result
    }

    fun parseLet(tk: Tokens, global: Boolean = false): Result<List<Declaration>> {
        val result = tk.AllOf(
            { FailIsAbsent(TokenKind.VAL) },
            TokenKind.NAME,
            { If(TokenKind.COLON, ::parseType) },
            { If(TokenKind.EQ, ::parseExpression) }
        ).map { sourceRef, (_, name, type, body) ->
            listOf(Declaration.Variable(name.text, body?.let { ExpressionRef(it, type) }, type, sourceRef, global))
        }
        return result
    }

    fun parseStruct(tk: Tokens, module: Module): Result<List<Declaration>> {
        val result = tk.AllOf(
            { FailIsAbsent({ OneOf(TokenKind.STRUCT, TokenKind.CLASS) }) },
            TokenKind.NAME,
            ::parseFunParams
        ).map { sourceRef, (kind, name, parameters) ->
            // Create struct declaration and constructor function together
            val fields = parameters.map { Field(it.name, it.type, it.sourceRef) }
            val structDecl = Declaration.Struct(name.text, fields, onHeap = kind.kind == TokenKind.CLASS, sourceRef = sourceRef)
            val structType = Type.Named(name.text, sourceRef, module.name, structDecl)
            val initList = parameters.map { param -> Expression.LoadVariable(param.name, param, param.sourceRef) }
            val body = Expression.New(initList, sourceRef, structType)
            val constructor = Declaration.Function(name.text, parameters, structType, ExpressionRef(body, structType), sourceRef = sourceRef)
            listOf(structDecl, constructor)
        }
        return result
    }

    fun parseInterface(tk: Tokens, module: Module): Result<List<Declaration>> {
        val result = tk.AllOf(
            { FailIsAbsent(TokenKind.INTERFACE) },
            TokenKind.NAME,
            { If(TokenKind.COLON, { CommaList(::parseTypeNamed, TokenKind.COMMA)} ) },
            { Repeat(::parseFun).map { _, it -> it.flatten() } },
            TokenKind.EOB
        ).map { sourceRef, (_, name, extensions, functions, _) ->
            val ifaceType = Type.Named(name.text, sourceRef, module.name)

            // The function prototypes on the interface
            val ifaceFuncs = functions.map { f ->
                val params = f.parameters.map { p -> Field(p.name, p.type, p.sourceRef) }
                InterfaceFunction(f.name, params, f.sourceRef, f.result)
            }

            // The global functions that use internal only mechanisms to invoke the interface method
//            val realFuncs = functions.mapIndexed { index, func ->
//                val self = Declaration.Variable("p\$self", null, ifaceType, sourceRef)
//                val params = func.parameters.mapIndexed { index, p ->
//                        Declaration.Variable("p\$$index", p.body, p.type, p.sourceRef)
//                    }
//                val body = Expression.InterfaceCall(
//                    Expression.LoadVariable("p\$self", self, func.sourceRef, ifaceType),
//                    index,
//                    Expression.Tuple(params.map { TupleField(it.name, Expression.LoadVariable(it.name, it, it.sourceRef, it.type), it.type, false) }, func.sourceRef),
//                    func.sourceRef,
//                    func.type
//                )
//                Declaration.Function(func.name, params, func.result, ExpressionRef(body, func.type), func.type, func.sourceRef, synthetic = true)
//            }

            // The interface declaration
            val iface = Declaration.Interface(name.text, ifaceFuncs, extensions ?: listOf(), name.sourceRef)

            ifaceType.declaration = iface

            // Return the global functions supporting this interface along with the interface itself
            listOf(iface)
        }
        return result
    }

    fun parseLocalDeclarations(tk: Tokens): Result<List<Declaration>> {
        val result = tk.Repeat { OneOf(::parseFun, ::parseLet) }.map { _, lists -> lists.flatten() }
        return result
    }

    fun parseGlobalDeclarations(tk: Tokens, module: Module): Result<List<Declaration>> {
        val result = tk.Repeat { OneOf({ parseStruct(this, module) }, { parseInterface(this, module) }, ::parseFun, { parseLet(this, global = true) } ) }
            .map { _, lists -> lists.flatten() }
        return result
    }

    fun createModuleAndPart(moduleName: String?, imports: PersistentList<Module>): Tuple2<Module, ModulePart> {
        val module = ast.findOrCreateModule(moduleName ?: "Anonymous\$${ast.modules.size}")
        val part = ModulePart(imports.add(ast.systemModule).add(module).distinct(), module)
        return tupleOf(module, part)
    }

    fun parseIntoAst(tk: Tokens): PersistentList<Pair<SourceRef, String>> {
        val headerResult = tk.AllOf(
            { If(TokenKind.MODULE, ::parseDottyName).map { _, b -> b?.joinToString(".") } },
            ::parseImports)

        val (module, part, bodyTk) = when (headerResult) {
            is Result.Fail -> return headerResult.error
            is Result.Absent -> createModuleAndPart(null, persistentListOf()) + tupleOf(tk)
            is Result.Ok -> createModuleAndPart(headerResult.value.v1, headerResult.value.v2) + tupleOf(headerResult.tokens)
        }

        val declarationsResult = parseGlobalDeclarations(bodyTk, module)

        val (declarations, endTk) = when (declarationsResult) {
            is Result.Fail -> return declarationsResult.error
            is Result.Absent -> tupleOf(listOf(), bodyTk)
            is Result.Ok -> tupleOf(declarationsResult.value, declarationsResult.tokens)
        }

        part.declarations.addAll(declarations)

        val token = endTk.head
        return if (token.kind != TokenKind.EOI) {
            persistentListOf(token.sourceRef to "Unexpected token ${token.kind}")
        } else {
            persistentListOf()
        }
    }
}

