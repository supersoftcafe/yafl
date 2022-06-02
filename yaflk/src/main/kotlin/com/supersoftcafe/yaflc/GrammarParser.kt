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
            val (type, t2, bits) = when {
                t1.endsWith("i1") -> tupleOf(ast.typeInt8, t1.dropLast(2), 8)
                t1.endsWith("i2") -> tupleOf(ast.typeInt16, t1.dropLast(2), 16)
                t1.endsWith("i4") -> tupleOf(ast.typeInt32, t1.dropLast(2), 32)
                t1.endsWith("i8") -> tupleOf(ast.typeInt64, t1.dropLast(2), 64)
                else -> tupleOf(ast.typeInt32, t1, 32)
            }
            val (radix, t3) = when {
                t2.startsWith("0b") -> tupleOf(2, t2.drop(2))
                t2.startsWith("0o") -> tupleOf(8, t2.drop(2))
                t2.startsWith("0d") -> tupleOf(10, t2.drop(2))
                t2.startsWith("0x") -> tupleOf(16, t2.drop(2))
                else -> tupleOf(10, t2)
            }

            val bigInt = t3.toBigInteger(radix)
            if (bigInt.bitLength() > (if (radix == 10) bits - 1 else bits))
                Result.Fail(token.sourceRef, "Integer out of range")
            else
                Result.Ok(Expression.LiteralInteger(bigInt.toLong(), token.sourceRef, type), token.sourceRef, token.tokens)
        }
        return result
    }

    fun parseLoadBuiltin(tk: Tokens): Result<Expression.LoadBuiltin> {
        val result = tk.AllOf({ FailIsAbsent(TokenKind.BUILTIN) }, TokenKind.NAME)
            .map { sourceRef, (_, name) -> Expression.LoadBuiltin(name.text, sourceRef) }
        return result
    }

    fun parseTupleExpr(tk: Tokens): Result<Expression.Tuple> {
        val result = tk.Parameters(
            { FailIsAbsent(TokenKind.OBRACKET) },
            { OneOf(
                { AllOf(TokenKind.NAME, TokenKind.EQ, ::parseExpression).map { sourceRef, (name, _, expr) -> TupleField(name.text, expr, null) } },
                { parseExpression(this).map { sourceRef, expr -> TupleField(null, expr, null) } }
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
            val param = Expression.Tuple(listOf(TupleField(null, expr, null)), expr.sourceRef)
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
            val param = Expression.Tuple(listOf(TupleField(null, left, null), TupleField(null, right, null)), left.sourceRef + right.sourceRef)
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

    fun parseDotExpr(tk: Tokens, nextLevel: Int): Result<Expression> {
        val result = tk.AllOf(
            { parseExpression(this, nextLevel) },
            { ListOfWhile(TokenKind.DOT, TokenKind.NAME) }
        ).map { sourceRef, (base, names) ->
            names.fold(base) { expr, name ->
                Expression.Dot(expr, name.text, sourceRef)
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
            11 -> parseCallExpr (tk, level + 1)
            12 -> parseDotExpr  (tk, level + 1)
            else -> tk.OneOf(::parseInteger, ::parseFloat, ::parseLoadBuiltin, ::parseNamed, ::parseTupleExpr)
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

    fun parseFun(tk: Tokens): Result<Declaration.Function> {
        val result = tk.AllOf(
            { FailIsAbsent(TokenKind.FUN) },
            TokenKind.NAME,
            ::parseFunParams,
            { If(TokenKind.COLON, ::parseType) },
            TokenKind.EQ,
            ::parseExpression
        ).map { sourceRef, (_, name, parameters, result, _, body) ->
            Declaration.Function(name.text, parameters, result, ExpressionRef(body, result), sourceRef = sourceRef)
        }
        return result
    }

    fun parseLet(tk: Tokens, global: Boolean): Result<Declaration.Variable> {
        val result = tk.AllOf(
            { FailIsAbsent(TokenKind.LET) },
            TokenKind.NAME,
            { If(TokenKind.COLON, ::parseType) },
            { If(TokenKind.EQ, ::parseExpression) }
        ).map { sourceRef, (_, name, type, body) ->
            Declaration.Variable(name.text, body?.let { ExpressionRef(it, type) }, type, sourceRef, global = global)
        }
        return result
    }

    fun parseLocalDeclarations(tk: Tokens): Result<PersistentList<Declaration>> {
        val result = tk.Repeat { OneOf(::parseFun, { parseLet(this, global = false) } ) }
        return result
    }

    fun parseGlobalDeclarations(tk: Tokens): Result<PersistentList<Declaration>> {
        // Not parameterised function because we'll also parse structs here in the future, unlike
        // local that will not parse structs
        val result = tk.Repeat { OneOf(::parseFun, { parseLet(this, global = true) } ) }
        return result
    }


    fun parseModulePart(tk: Tokens): Result<ModulePart> {
        val result = tk.AllOf(
            { If(TokenKind.MODULE, ::parseDottyName).map { _, b -> b?.joinToString(".") } },
            ::parseImports,
            ::parseGlobalDeclarations)
            .map { _, (moduleName, imports, declarations) ->
                val module = ast.findOrCreateModule(moduleName ?: "Anonymous\$${ast.modules.size}")
                val part = ModulePart(imports.add(ast.systemModule).add(module).distinct(), module)
                part.declarations.addAll(declarations)
                part
            }
        return result
    }

    fun parseIntoAst(tokens: Tokens): PersistentList<Pair<SourceRef, String>> {
        return when (val part = parseModulePart(tokens)) {
            is Result.Absent -> persistentListOf(part.sourceRef to "Failed to find a module section")
            is Result.Fail -> part.error
            is Result.Ok -> {
                val token = part.tokens.get()
                if (token.value.kind != TokenKind.EOI)
                    persistentListOf(token.sourceRef to "Unexpected token ${token.value.kind}")
                else
                    persistentListOf()
            }
        }
    }
}

