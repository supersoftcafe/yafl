package com.supersoftcafe.yaflc

import kotlinx.collections.immutable.persistentListOf

class TypeResolver(val ast: Ast) {

    private fun Module.findDeclarations(matcher: (Declaration) -> Boolean): List<Declaration> {
        val result = parts.flatMap {  it.declarations.filter(matcher) }
        return result
    }

    private fun NodePath.findDeclarations(matcher: (Declaration) -> Boolean): List<Declaration> {
        val node = firstOrNull() ?: return listOf()
        val parents = removeAt(0).findDeclarations(matcher)
        val result = when (node) {
            is Declaration.Function -> parents + node.parameters.filter(matcher)
            is Expression.DeclareLocal -> parents + node.declarations.filter(matcher)
            is ModulePart -> parents + node.imports.flatMap {
                it.findDeclarations(matcher)
            }
            else -> parents
        }
        return result
    }

    fun List<Field>.maybeEquals(other: List<Field>): Boolean {
        return size == other.size && zip(other).all { (l,r) -> l.type.maybeEquals(r.type) }
    }

    fun Type?.maybeEquals(other: Any?): Boolean {
        return if (this == null || other == null) true
        else when (this) {
            is Type.Named -> other is Type.Named && (declaration == null || other.declaration == null || declaration == other.declaration)
            is Type.Tuple -> other is Type.Tuple && other.fields.maybeEquals(fields)
            is Type.Function -> other is Type.Function && other.result.maybeEquals(result) && other.parameter.fields.maybeEquals(parameter.fields)
        }
    }




    fun primitiveToType(kind: PrimitiveKind): Type {
        return when (kind) {
            PrimitiveKind.Bool -> ast.typeBool
            PrimitiveKind.Int8 -> ast.typeInt8
            PrimitiveKind.Int16 -> ast.typeInt16
            PrimitiveKind.Int32 -> ast.typeInt32
            PrimitiveKind.Int64 -> ast.typeInt64
            PrimitiveKind.Float32 -> ast.typeFloat32
            PrimitiveKind.Float64 -> ast.typeFloat64
        }
    }

    fun resolveFieldType(nodePath: NodePath, field: Field): Errors {
        return resolveType(nodePath, field.type
            ?: return persistentListOf(field.sourceRef to "Unknown expression type"))
    }

    fun resolveTypeFunction(nodePath: NodePath, type: Type.Function): Errors {
        val result = type.result
            ?: return persistentListOf(type.sourceRef to "Function type has undefined result")
        return resolveTypeTuple(nodePath, type.parameter).addAll(resolveType(nodePath, result))
    }

    fun resolveTypeNamed(nodePath: NodePath, type: Type.Named): Errors {
        fun matcher(d: Declaration) = (d is Declaration.Struct || d is Declaration.Primitive) && d.name == type.typeName

        val found = if (type.moduleName != null) {
            val module = ast.modules.firstOrNull { it.name == type.moduleName }
                ?: return persistentListOf(type.sourceRef to "Cannot find module")
            module.findDeclarations(::matcher)
        } else {
            nodePath.findDeclarations(::matcher)
        }

        if (found.size > 1)
            return persistentListOf(type.sourceRef to "Multiple matches found")

        type.declaration = found.firstOrNull()
            ?: return persistentListOf(type.sourceRef to "No matches found")

        return persistentListOf()
    }

    fun resolveTypeTuple(nodePath: NodePath, type: Type.Tuple): Errors {
        return type.fields.foldErrors { resolveFieldType(nodePath, it) }
    }

    fun resolveType(nodePath: NodePath, type: Type): Errors {
        val errors = when (type) {
            is Type.Function -> resolveTypeFunction(nodePath, type)
            is Type.Named -> resolveTypeNamed(nodePath, type)
            is Type.Tuple -> resolveTypeTuple(nodePath, type)
        }
        return errors
    }




    fun resolveExpressionLoadVariable(nodePath: NodePath, expression: Expression.LoadVariable, reference: ExpressionRef): Errors {
        val newNodePath = nodePath.add(expression)

        if (expression.variable == null) {
            // Find anything that matches the expression type. Might over-fetch on first few passes whilst type == null.
            fun matcher(d: Declaration): Boolean =
                d.name == expression.name && (d is Declaration.Variable || d is Declaration.Function) && d.type.maybeEquals(expression.type)
            var candidates = nodePath.findDeclarations(::matcher)

            // If we find too many candidates, try to reduce further using the receiver type
            if (candidates.size > 1)
                candidates = candidates.filter { it.type.maybeEquals(reference.receiver) }

            if (candidates.size > 1)
                return persistentListOf(expression.sourceRef to "Ambiguous variable name")


            expression.variable = candidates.firstOrNull()
        }

        val variable = expression.variable
            ?: return persistentListOf(expression.sourceRef to "Unknown variable reference")

        when (variable) {
            is Declaration.Variable -> {
                if (variable.type == null && reference.receiver != null)
                    variable.type = reference.receiver
            }
            is Declaration.Function -> {
                // If any of the parameter types are unknown, and we know the type, update the parameter
                val receiver = reference.receiver
                if (receiver is Type.Function) {
                    for ((param, input) in variable.parameters.zip(receiver.parameter.fields))
                        if (param.type == null)
                            param.type = input.type
                    if (variable.result == null)
                        variable.result = receiver.result
                }
            }
        }

        if (expression.type == null) {
            expression.type = variable.type
            if (expression.type == null)
                return persistentListOf(expression.sourceRef to "Load variable type mismatch")
        }
        return persistentListOf()
    }

    fun resolveExpressionLoadBuiltin(nodePath: NodePath, expression: Expression.LoadBuiltin, reference: ExpressionRef): Errors {
        if (expression.builtinOp == null)
            expression.builtinOp = ast.builtinOps.firstOrNull { it.name == expression.name }
        val op = expression.builtinOp
            ?: return persistentListOf(expression.sourceRef to "Unknown built in operation")

        if (expression.type == null)
            expression.type = Type.Function(op.parameter, op.result, expression.sourceRef)

        return persistentListOf()
    }

    fun resolveExpressionCall(nodePath: NodePath, expression: Expression.Call, reference: ExpressionRef): Errors {
        val target = expression.children.first()
        val parameter = expression.children.last()
        val tuple = Type.Tuple((parameter.expression as? Expression.Tuple)?.children?.filterIsInstance<TupleField>()?.mapIndexed { index, it -> Field(it.name ?: "value$index", it.expression.type, SourceRef.EMPTY) } ?: listOf(), SourceRef.EMPTY)

        parameter.receiver = (target.expression.type as? Type.Function)?.parameter
        target.receiver = Type.Function(tuple, reference.receiver, SourceRef.EMPTY)

        if (expression.type == null) {
            val type = (target.expression.type as? Type.Function)?.result
            if (type != null)
                expression.type = type
        }

        return persistentListOf()
    }

    fun resolveExpressionLiteralInteger(nodePath: NodePath, expression: Expression.LiteralInteger, reference: ExpressionRef): Errors {
        if (expression.type == null)
            return persistentListOf(expression.sourceRef to "Compiler Bug: Unknown type")
        return persistentListOf()
    }

    fun resolveExpressionLiteralBool(nodePath: NodePath, expression: Expression.LiteralBool, reference: ExpressionRef): Errors {
        if (expression.type == null)
            return persistentListOf(expression.sourceRef to "Compiler Bug: Unknown type")
        return persistentListOf()
    }

    fun resolveExpressionDeclareLocal(nodePath: NodePath, expression: Expression.DeclareLocal, reference: ExpressionRef): Errors {
        val declarations = expression.declarations
        if (expression.type == null)
            expression.type = declarations.last().type

        val tail = expression.children.last()
        tail.receiver = reference.receiver

        val result = declarations.foldErrors { declaration ->
            when (declaration) {
                is Declaration.Variable -> {
                    val body = declaration.body!!
                    if (declaration.type != null) {
                        body.receiver = declaration.type
                    } else if (body.expression.type != null) {
                        declaration.type = body.expression.type
                    }
                    if (declaration.type != body.expression.type) {
                        persistentListOf(declaration.sourceRef to "Incompatible expression type for declaration")
                    } else {
                        persistentListOf()
                    }
                }
                is Declaration.Function -> TODO()
                else -> throw IllegalArgumentException("${declaration::class.simpleName} cannot be a local declaration")
            }
        }
        return result
    }

    fun resolveExpressionCondition(nodePath: NodePath, expression: Expression.Condition, reference: ExpressionRef): Errors {
        val children = expression.children
        val conditionExpr = children[0]
        val trueExpr = children[1]
        val falseExpr = children[2]

        conditionExpr.receiver = ast.typeBool
        trueExpr.receiver = reference.receiver ?: falseExpr.expression.type
        falseExpr.receiver = reference.receiver ?: trueExpr.expression.type

        if (conditionExpr.expression.type != ast.typeBool)
            return persistentListOf(conditionExpr.expression.sourceRef to "Expected boolean type")
        if (trueExpr.expression.type != null && trueExpr.expression.type != falseExpr.expression.type)
            return persistentListOf((trueExpr.expression.sourceRef + falseExpr.expression.sourceRef) to "Left and right of condition must have matching types")

        expression.type = trueExpr.expression.type

        return persistentListOf()
    }

    fun resolveExpressionLoadField(nodePath: NodePath, expression: Expression.LoadField, reference: ExpressionRef): Errors {
        val base = expression.children[0]

        when (val type = base.expression.type) {
            is Type.Tuple -> {
                base.receiver = type

                val fieldIndex = type.fields.indexOfFirst { it.name == expression.fieldName }
                if (fieldIndex == -1)
                    return persistentListOf(expression.sourceRef to "Field ${expression.fieldName} not found")

                expression.type = type.fields[fieldIndex].type
                expression.fieldIndex = fieldIndex
                return persistentListOf()
            }
            is Type.Named -> {
                when (val declaration = type.declaration) {
                    is Declaration.Struct -> {
                        base.receiver = type

                        val fieldIndex = declaration.fields.indexOfFirst { it.name == expression.fieldName }
                        if (fieldIndex == -1)
                            return persistentListOf(expression.sourceRef to "Field ${expression.fieldName} not found")

                        val field = declaration.fields[fieldIndex]

                        if (expression.type == null)
                            expression.type = field.type

                        expression.fieldIndex = fieldIndex
                        return persistentListOf()
                    }
                    else -> {
                        return persistentListOf(expression.sourceRef to "Tuple or Struct expected")
                    }
                }
            }
            else -> {
                return persistentListOf(expression.sourceRef to "Tuple or Struct expected")
            }
        }
    }

    fun resolveExpressionTuple(nodePath: NodePath, expression: Expression.Tuple, reference: ExpressionRef): Errors {
        val children = expression.children.filterIsInstance<TupleField>().toList()
        val receiverFields = (reference.receiver as? Type.Tuple)?.fields ?: listOf()

        if (expression.type == null && children.all { it.expression.type != null }) {
            expression.type = Type.Tuple(children.mapIndexed { index, field ->
                Field(field.name ?: "value$index", field.expression.type, field.expression.sourceRef)
            }, expression.sourceRef)
        }

        val errors = if (children.size != receiverFields.size) {
            persistentListOf(expression.sourceRef to "Incorrect number of tuple fields")
        } else {
            for ((ref, field) in children.zip(receiverFields))
                ref.receiver = field.type
            persistentListOf()
        }

        return errors
    }

    fun resolveExpressionNew(nodePath: NodePath, expression: Expression.New, reference: ExpressionRef): Errors {
        val children = expression.children
        val struct = (expression.type!! as Type.Named).declaration as Declaration.Struct

        for ((exprRef, field) in children.zip(struct.fields)) {
            if (field.type == null && exprRef.expression.type.isComplete())
                field.type = exprRef.expression.type
            exprRef.receiver = field.type
        }

        return persistentListOf()
    }



    fun resolveExpressionChildren(nodePath: NodePath, expression: Expression, reference: ExpressionRef): Errors {
        val newNodePath = nodePath.add(expression)
        return expression.children.foldErrors {
            resolveExpression(newNodePath, it.expression, it)
        }
    }

    fun resolveExpressionByType(nodePath: NodePath, expression: Expression, reference: ExpressionRef): Errors {
        return when (expression) {
            is Expression.LoadVariable -> resolveExpressionLoadVariable(nodePath, expression, reference)
            is Expression.LoadBuiltin -> resolveExpressionLoadBuiltin(nodePath, expression, reference)
            is Expression.Call -> resolveExpressionCall(nodePath, expression, reference)
            is Expression.Condition -> resolveExpressionCondition(nodePath, expression, reference)
            is Expression.DeclareLocal -> resolveExpressionDeclareLocal(nodePath, expression, reference)
            is Expression.Lambda -> TODO()
            is Expression.LiteralFloat -> TODO()
            is Expression.LiteralBool -> resolveExpressionLiteralBool(nodePath, expression, reference)
            is Expression.LiteralInteger -> resolveExpressionLiteralInteger(nodePath, expression, reference)
            is Expression.LiteralString -> TODO()
            is Expression.Tuple -> resolveExpressionTuple(nodePath, expression, reference)
            is Expression.StoreVariable -> TODO()
            is Expression.LoadField -> resolveExpressionLoadField(nodePath, expression, reference)
            is Expression.New -> resolveExpressionNew(nodePath, expression, reference)
        }
    }

    fun resolveExpressionReceiver(nodePath: NodePath, expression: Expression, reference: ExpressionRef): Errors {
        val receiver = reference.receiver
        return if (receiver != null && receiver == expression.type)
            persistentListOf()
        else
            persistentListOf(expression.sourceRef to "Does not match receiver type")
    }

    fun resolveExpression(nodePath: NodePath, expression: Expression, reference: ExpressionRef): Errors {
        return      resolveExpressionByType  (nodePath, expression, reference)
            .addAll(resolveExpressionChildren(nodePath, expression, reference))
            .addAll(resolveExpressionReceiver(nodePath, expression, reference))
    }



    fun resolveVariable(nodePath: NodePath, variable: Declaration.Variable, isParameter: Boolean): Errors {
        val newNodePath = nodePath.add(variable)

        val expression = variable.body?.expression
        if (expression == null && !isParameter)
            return persistentListOf(variable.sourceRef to "Variable missing initializer expression")

        var errors = persistentListOf<Pair<SourceRef, String>>()

        if (expression != null) {
            variable.body.receiver = variable.type
            errors = errors.addAll(resolveExpression(newNodePath, expression, variable.body))
//            if (variable.type == null)
//                variable.type = expression.type
        }

        if (variable.type != null) {
            resolveType(nodePath, variable.type!!)
        } else  {
            if (expression != null)
                variable.type = expression.type
            if (variable.type == null)
                errors = errors.add(variable.sourceRef to "Unknown variable type")
        }

        return errors
    }

    fun resolvePrimitive(nodePath: NodePath, primitive: Declaration.Primitive): Errors {
        return persistentListOf()
    }

    fun resolveStruct(nodePath: NodePath, struct: Declaration.Struct): Errors {
        val newNodePath = nodePath.add(struct)
        val result = struct.fields.foldErrors { resolveFieldType(newNodePath, it) }
        return result
    }

    fun resolveFunction(nodePath: NodePath, function: Declaration.Function): Errors {
        val newNodePath = nodePath.add(function)

        function.body.receiver = function.result

        // TODO: Derive parameter types from the body. For now though we require them to be specified
        var errors = function.parameters.foldErrors { resolveVariable(newNodePath, it, true) }
            .addAll( resolveExpression(newNodePath, function.body.expression, function.body) )

        val result = function.result ?: function.body.expression.type
        function.result = result ?: return errors.add(function.sourceRef to "Cannot determine result type")

        if (function.type == null && function.parameters.all { it.type != null })
            function.type = Type.Function(Type.Tuple(function.parameters.map { Field(it.name, it.type, it.sourceRef) }, function.sourceRef), result, function.sourceRef)

        if (function.type != null)
            errors = errors.addAll(resolveType(newNodePath, function.type!!))
        errors = errors.addAll(resolveType(newNodePath, result))

        return errors
    }

    fun resolveDeclaration(nodePath: NodePath, declaration: Declaration): Errors {
        val result = when (declaration) {
            is Declaration.Function -> resolveFunction(nodePath, declaration)
            is Declaration.Variable -> resolveVariable(nodePath, declaration, false)
            is Declaration.Primitive -> resolvePrimitive(nodePath, declaration)
            is Declaration.Struct -> resolveStruct(nodePath, declaration)
        }
        return result
    }

    fun resolveModulePart(part: ModulePart): Errors {
        val newNodePath = persistentListOf(part)
        val errors = part.declarations.foldErrors { resolveDeclaration(newNodePath, it) }
        return errors
    }

    fun resolveModule(module: Module): Errors {
        val errors = module.parts.foldErrors(::resolveModulePart)
        return errors
    }

    fun createInitFunction(): Errors {
        val mains = mutableListOf<Declaration.Function>()
        for (module in ast.modules) {
            for (part in module.parts) {
                for (declaration in part.declarations) {
                    if (declaration is Declaration.Function && declaration.name == "main" && declaration.result == ast.typeInt32 && declaration.parameters.isEmpty()) {
                        mains += declaration
                    }
                }
            }
        }

        if (mains.size > 1)
            return persistentListOf(SourceRef.EMPTY to "Too many main methods found")
        val main = mains.firstOrNull()
            ?: return persistentListOf(SourceRef.EMPTY to "No 'fun main():Int32' found")

        val variables = mutableListOf<Declaration.Variable>()
        for (module in ast.modules) {
            for (part in module.parts) {
                for (declaration in part.declarations) {
                    if (declaration is Declaration.Variable) {
                        variables += declaration
                    }
                }
            }
        }

        val mainType = Type.Function(Type.Tuple(listOf(), SourceRef.EMPTY), ast.typeInt32, SourceRef.EMPTY)
        val unitExpr = Expression.Tuple(listOf(), SourceRef.EMPTY, Type.Tuple(listOf(), SourceRef.EMPTY))
        val callMain = Expression.Call(
            Expression.LoadVariable(main.name, main, SourceRef.EMPTY, mainType),
            unitExpr,
            main.sourceRef,
            ast.typeInt32
        )
        val initVars = variables.reversed().fold<Declaration.Variable, Expression>(callMain) { tail, variable  ->
            Expression.StoreVariable(
                variable.name,
                variable,
                variable.body!!.expression,
                tail,
                variable.sourceRef,
                ast.typeInt32
            )
        }
        val initFunction = Declaration.Function(
            "main",
            listOf(),
            ast.typeInt32,
            ExpressionRef(initVars, ast.typeInt32),
            mainType,
            SourceRef.EMPTY,
            synthetic = true
        )

        ast.syntheticModulePart.declarations += initFunction

        return persistentListOf()
    }

    fun resolve(lastErrors: Errors = persistentListOf()): Errors {
        val errors = ast.modules.foldErrors(::resolveModule)
        return if (errors != lastErrors)
            resolve(errors)
        else if (errors.isEmpty())
            createInitFunction()
        else
            errors
    }
}