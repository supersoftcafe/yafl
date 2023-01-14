package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.*
import com.supersoftcafe.yafl.utils.Namer


private class InferTypesErrorScan(val globals: Map<Namer, Declaration>, val hints: TypeHints) : AbstractErrorScan() {
    override fun scan(self: TypeRef?, sourceRef: SourceRef): List<String> {
        return when (self) {
            null ->
                listOf("$sourceRef unknown type")

            is TypeRef.Unresolved ->
                listOf("$sourceRef unresolved type '${self.name}'")

            is TypeRef.Tuple ->
                self.fields.flatMap { scan(it.typeRef, sourceRef) }

            is TypeRef.Callable ->
                scan(self.result, sourceRef) + scan(self.parameter, sourceRef)

            is TypeRef.Named ->
                listOf()

            is TypeRef.Primitive ->
                listOf()

            TypeRef.Unit ->
                listOf()
        }
    }

    override fun scan(self: DataRef?, sourceRef: SourceRef): List<String> {
        return when (self) {
            null ->
                listOf("$sourceRef unknown reference")

            is DataRef.Unresolved ->
                listOf("$sourceRef unresolved reference '${self.name}'")

            is DataRef.Resolved ->
                listOf()
        }
    }

    private fun getKlassParam(self: Expression.LoadMember): Triple<Declaration.Klass, Declaration, Long?> {
        val klass = globals[(self.base.typeRef as TypeRef.Named).id] as Declaration.Klass
        val param = klass.parameters.firstOrNull { it.id == self.id } ?: klass.members.first { it.id == self.id }
        return Triple(klass, param, (param as? Declaration.Let)?.arraySize)
    }


    override fun scan(self: Expression?, parent: Expression?): List<String> {
        return super.scan(self, parent).ifEmpty {
            when (self) {
                is Expression.ArrayLookup -> {
                    if (self.array !is Expression.LoadMember) {
                        listOf("${self.sourceRef} array lookup can only be applied to class members")
                    } else {
                        val (klass, member, arraySize) = getKlassParam(self.array)

                        if (arraySize == null)
                            listOf("${self.sourceRef} member is not an array")
                        else if (self.index is Expression.Integer && (self.index.value < 0 || self.index.value >= arraySize))
                            listOf("${self.index.sourceRef} array index out of bounds")
                        else
                            listOf()
                    }
                }

                is Expression.If -> {
                    listOfNotNull(
                        if (self.condition.typeRef != TypeRef.Bool)
                            "${self.condition.sourceRef} is not a boolean expression"
                        else null,
                        if (self.typeRef == null)
                            "${self.sourceRef} conditional branch types are not compatible"
                        else null
                    )
                }

                is Expression.Call -> {
                    val targetParams = (self.callable.typeRef as TypeRef.Callable).parameter!!.fields
                    val sourceParams = (self.parameter.typeRef as TypeRef.Tuple).fields

                    if (targetParams.size != sourceParams.size) {
                        listOf("${self.parameter.sourceRef} parameter count does not match function requirements")
                    } else {
                        targetParams.mapIndexedNotNull { index, target ->
                            val source = sourceParams[index]
                            if (!target.typeRef.isAssignableFrom(source.typeRef))
                                "${self.parameter.sourceRef} parameter $index does not match target type"
                            else null
                        }
                    }
                }

                is Expression.LoadMember -> {
                    val (klass, param, arraySize) = getKlassParam(self)

                    listOfNotNull(
                        if (self.id != null) null
                        else "${self.sourceRef} member ${self.name} not found",

                        if (parent is Expression.ArrayLookup || arraySize == null) null
                        else "${self.sourceRef} member is an array"
                    )
                }

                else -> listOf()
            }
        }
    }

    override fun scanFunction(self: Declaration.Function): List<String> {
        return super.scanFunction(self).ifEmpty {
            listOfNotNull(
                if (self.scope != Scope.Global || self.body != null || "extern" in self.attributes)
                    null
                else
                    "${self.sourceRef} function declared without body",

                if (self.body == null || self.returnType.isAssignableFrom(self.body.typeRef))
                    null
                else
                    "${self.sourceRef} incompatible function return type and expression"
            )
        }
    }

    override fun scanLet(self: Declaration.Let): List<String> {
        return super.scanLet(self).ifEmpty {
            listOfNotNull(
                if (self.body == null || self.typeRef.isAssignableFrom(self.body.typeRef))
                    null
                else
                    "${self.sourceRef} incompatible types between let and expression"
            )
        }
    }

    override fun scanKlass(self: Declaration.Klass): List<String> {
        return super.scanKlass(self).ifEmpty {
            // If there have been no errors in the inherited interfaces, check for correct function overrides etc
            if (self.extends.filterIsInstance<TypeRef.Named>().any { scan(globals[it.id]).isNotEmpty() }) {
                listOf()
            } else {
                val members = self.flattenClassMembersBySignature { name, id -> globals[id]!! }

                members
                    // No ambiguity with duplicate inherited implementations
                    .filterValues { it.size > 1 }
                    .map { (key, list) ->
                        val func = list.first()
                        "${func.sourceRef} Multiple implementations of ${func.name}"
                    } + if (self.isInterface) listOf() else
                // No unimplemented functions
                    members
                        .filterValues { it.first().body == null }
                        .map { (key, list) ->
                            val func = list.first()
                            "${func.sourceRef} Unimplemented"
                        }
            }
        }
    }
}



fun inferTypesErrorScan(ast: Ast): List<String> {
    return InferTypesErrorScan(
        ast.declarations.associate { (_, declaration, _) -> declaration.id to declaration },
        ast.typeHints
    ).scan(ast)
}
