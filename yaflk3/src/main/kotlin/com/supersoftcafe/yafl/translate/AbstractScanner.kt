package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*

abstract class AbstractScanner<TResult> {
    open fun scanSource(self: TypeRef?, sourceRef: SourceRef): List<TResult> {
        return listOf()
    }

    open fun scan(self: TypeRef?, sourceRef: SourceRef): List<TResult> {
        return listOf()
    }

    open fun scan(self: DataRef?, sourceRef: SourceRef): List<TResult> {
        return listOf()
    }

    open fun scan(self: Expression?, parent: Expression?): List<TResult> {
        return if (self == null) listOf()
        else scan(self.typeRef, self.sourceRef).ifEmpty {
            when (self) {
                is Expression.Let ->
                    scan(self.let) + scan(self.tail, self)

                is Expression.Assert ->
                    scan(self.value, self) + scan(self.condition, self)

                is Expression.ArrayLookup ->
                    scan(self.array, self) + scan(self.index, self)

                is Expression.NewKlass ->
                    scan(self.parameter, self)

                is Expression.Llvmir ->
                    self.inputs.flatMap {
                        scan(it, self)
                    }

                is Expression.Call ->
                    scan(self.callable, self) + scan(self.parameter, self)

                is Expression.Tuple ->
                    self.fields.flatMap {
                        scan(it.expression, self)
                    }

                is Expression.Lambda ->
                    scan(self.body, self) +
                            self.parameters.flatMap {
                                scan(it)
                            }

                is Expression.If ->
                    scan(self.condition, self) +
                            scan(self.ifTrue, self) +
                            scan(self.ifFalse, self)

                is Expression.LoadMember ->
                    scan(self.base, self)

                is Expression.LoadData ->
                    scan(self.dataRef, self.sourceRef)

                is Expression.Characters, is Expression.Float, is Expression.Integer ->
                    scan(self.typeRef, self.sourceRef)
            }
        }
    }

    open fun scanFunction(self: Declaration.Function): List<TResult> {
        return scanSource(self.sourceReturnType, self.sourceRef).ifEmpty { scan(self.returnType, self.sourceRef) } +
                scan(self.thisDeclaration) +
                self.parameters.flatMap { scan(it) } +
                scan(self.body, null)
    }

    open fun scanLet(self: Declaration.Let): List<TResult> {
        return scanSource(self.sourceTypeRef, self.sourceRef).ifEmpty {
            scan(self.typeRef, self.sourceRef)
        } + scan(self.body, null) +
            scan(self.dynamicArraySize, null)
    }

    open fun scanAlias(self: Declaration.Alias): List<TResult> {
        return scan(self.typeRef, self.sourceRef)
    }

    open fun scanKlass(self: Declaration.Klass): List<TResult> {
        return self.parameters.flatMap { scanLet(it) } +
                self.members.flatMap { scanFunction(it) } +
                self.extends.flatMap { scan(it, self.sourceRef) }
    }

    open fun scan(self: Declaration?): List<TResult> {
        return when (self) {
            null -> listOf()
            is Declaration.Function -> scanFunction(self)
            is Declaration.Let -> scanLet(self)
            is Declaration.Klass -> scanKlass(self)
            is Declaration.Alias -> scanAlias(self)
        }
    }

    open fun scan(ast: Ast): List<TResult> {
        return ast.declarations.flatMap { (_, declaration, _) ->
            scan(declaration)
        }
    }
}