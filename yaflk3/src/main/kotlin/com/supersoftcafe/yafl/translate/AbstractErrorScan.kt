package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*

abstract class AbstractErrorScan {
    protected open fun scanSource(self: TypeRef?, sourceRef: SourceRef): List<String> {
        return listOf()
    }

    protected open fun scan(self: TypeRef?, sourceRef: SourceRef): List<String> {
        return listOf()
    }

    protected open fun scan(self: DataRef?, sourceRef: SourceRef): List<String> {
        return listOf()
    }

    protected open fun scan(self: Expression?): List<String> {
        return if (self == null) listOf()
        else scan(self.typeRef, self.sourceRef).ifEmpty {
            when (self) {
                is Expression.NewArray ->
                    self.elements.flatMap { scan(it) }.ifEmpty { scan(self.typeRef, self.sourceRef) }

                is Expression.ArrayLookup ->
                    scan(self.array) + scan(self.index)

                is Expression.NewKlass ->
                    scan(self.parameter)

                is Expression.Llvmir ->
                    self.inputs.flatMap {
                        scan(it)
                    }

                is Expression.Call ->
                    scan(self.callable) +
                            scan(self.parameter)

                is Expression.Tuple ->
                    self.fields.flatMap {
                        scan(it.expression)
                    }

                is Expression.Lambda ->
                    scan(self.body) +
                            self.parameters.flatMap {
                                scan(it)
                            }

                is Expression.If ->
                    scan(self.condition) +
                            scan(self.ifTrue) +
                            scan(self.ifFalse)

                is Expression.LoadMember ->
                    scan(self.base)

                is Expression.LoadData ->
                    scan(self.dataRef, self.sourceRef)

                is Expression.Characters, is Expression.Float, is Expression.Integer ->
                    scan(self.typeRef, self.sourceRef)
            }
        }
    }

    protected open fun scanFunction(self: Declaration.Function): List<String> {
        return scanSource(self.sourceReturnType, self.sourceRef).ifEmpty { scan(self.returnType, self.sourceRef) } +
                scan(self.thisDeclaration) +
                self.parameters.flatMap { scan(it) } +
                scan(self.body)
    }

    protected open fun scanLet(self: Declaration.Let): List<String> {
        return scanSource(self.sourceTypeRef, self.sourceRef).ifEmpty {
            scan(self.typeRef, self.sourceRef)
        } +
            scan(self.body)
    }

    protected open fun scanAlias(self: Declaration.Alias): List<String> {
        return scan(self.typeRef, self.sourceRef)
    }

    protected open fun scanKlass(self: Declaration.Klass): List<String> {
        return self.parameters.flatMap { scanLet(it) } +
                self.members.flatMap { scanFunction(it) } +
                self.extends.flatMap { scan(it, self.sourceRef) }
    }

    protected open fun scan(self: Declaration?): List<String> {
        return when (self) {
            null -> listOf()
            is Declaration.Function -> scanFunction(self)
            is Declaration.Let -> scanLet(self)
            is Declaration.Klass -> scanKlass(self)
            is Declaration.Alias -> scanAlias(self)
        }
    }

    open fun scan(ast: Ast): List<String> {
        return ast.declarations.flatMap { (_, declaration, _) ->
            scan(declaration)
        }
    }
}