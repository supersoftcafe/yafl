package com.supersoftcafe.yafl.passes.p3_infer

import com.supersoftcafe.yafl.models.ast.*
import com.supersoftcafe.yafl.passes.AbstractScanner
import com.supersoftcafe.yafl.utils.ErrorInfo
import com.supersoftcafe.yafl.utils.Namer
import com.supersoftcafe.yafl.utils.tupleOf


private class InferTypesErrorScan(val globals: Map<Namer, Declaration>, val hints: TypeHints) : AbstractScanner<ErrorInfo>() {
    override fun scan(self: TypeRef?, sourceRef: SourceRef): List<ErrorInfo> {
        return when (self) {
            null ->
                listOf(ErrorInfo.StringWithSourceRef(sourceRef, "unknown type"))

            is TypeRef.Unresolved ->
                listOf(ErrorInfo.StringWithSourceRef(sourceRef, "unresolved type '${self.name}'"))

            is TypeRef.Tuple ->
                self.fields.flatMap { scan(it.typeRef, sourceRef) }

            is TypeRef.TaggedValues ->
                self.tags.flatMap { scan(it.typeRef, sourceRef) }

            is TypeRef.Callable ->
                scan(self.result, sourceRef) + scan(self.parameter, sourceRef)

            is TypeRef.Klass, is TypeRef.Primitive ->
                listOf()
        }
    }

    override fun scan(self: DataRef?, sourceRef: SourceRef): List<ErrorInfo> {
        return when (self) {
            null ->
                listOf(ErrorInfo.StringWithSourceRef(sourceRef, "unknown reference"))

            is DataRef.Unresolved ->
                listOf(ErrorInfo.StringWithSourceRef(sourceRef, "unresolved reference '${self.name}'"))

            is DataRef.Resolved ->
                listOf()
        }
    }

    private fun getKlassParam(self: Expression.LoadMember): Triple<Declaration.Klass, Declaration, Long?> {
        val klass = globals[(self.base.typeRef as TypeRef.Klass).id] as Declaration.Klass
        val param = klass.parameters.firstOrNull { it.id == self.id } ?: klass.members.first { it.id == self.id }
        return Triple(klass, param, (param as? Declaration.Let)?.arraySize)
    }


    override fun scan(self: Expression?, parent: Expression?): List<ErrorInfo> {
        return super.scan(self, parent).ifEmpty {
            when (self) {
                is Expression.RawPointer ->
                    if (self.field !is Expression.LoadMember) {
                        listOf(ErrorInfo.StringWithSourceRef(self.field.sourceRef, "raw pointer must use a field access expression"))

                    } else {
                        val typeRef = self.field.base.typeRef as? TypeRef.Klass
                        val klass = globals[typeRef?.id] as? Declaration.Klass
                        val field = klass?.parameters?.firstOrNull { it.id == self.field.id }

                        if (klass?.isInterface == true) {
                            listOf(ErrorInfo.StringWithSourceRef(self.sourceRef, "raw pointer expression not allowed on interfaces"))
                        } else if (field == null) {
                            listOf(ErrorInfo.StringWithSourceRef(self.sourceRef, "raw pointer expression does not refer to a class field"))
                        } else {
                            listOf()
                        }
                    }

                is Expression.Assert ->
                    if (self.condition.typeRef != TypeRef.Bool)
                        listOf(ErrorInfo.StringWithSourceRef(self.condition.sourceRef, "condition expression is not boolean"))
                    else
                        listOf()

                is Expression.ArrayLookup ->
                    if (self.array !is Expression.LoadMember) {
                        listOf(ErrorInfo.StringWithSourceRef(self.sourceRef, "array lookup can only be applied to class members"))
                    } else {
                        val (klass, member, arraySize) = getKlassParam(self.array)

                        if (arraySize == null)
                            listOf(ErrorInfo.StringWithSourceRef(self.sourceRef, "member is not an array"))
                        else if (self.index is Expression.Integer && (self.index.value < 0 || self.index.value >= arraySize))
                            listOf(ErrorInfo.StringWithSourceRef(self.index.sourceRef, "array index out of bounds"))
                        else
                            listOf()
                    }

                is Expression.If ->
                    listOfNotNull(
                        if (self.condition.typeRef != TypeRef.Bool)
                            ErrorInfo.StringWithSourceRef(self.condition.sourceRef, "is not a boolean expression")
                        else null,
                        if (self.typeRef == null)
                            ErrorInfo.StringWithSourceRef(self.sourceRef, "conditional branch types are not compatible")
                        else null
                    )

                is Expression.When ->
                    listOfNotNull(
                        if (self.condition.typeRef !is TypeRef.TaggedValues)
                            ErrorInfo.StringWithSourceRef(self.condition.sourceRef, "is not a tagged value")
                        else null,
                        if (self.typeRef == null)
                            ErrorInfo.StringWithSourceRef(self.sourceRef, "conditional branch types are not compatible")
                        else null
                    )

                is Expression.Call -> {
                    val callableParamType = (self.callable.typeRef as? TypeRef.Callable)?.parameter
                    val providedParamType = self.parameter.typeRef

                    if (!callableParamType.isAssignableFrom(providedParamType))
                         listOf(ErrorInfo.StringWithSourceRef(self.parameter.sourceRef, "parameter does not match function requirements"))
                    else listOf()
                }

                is Expression.Parallel -> {
                    scan(self.parameter, self)
                }

                is Expression.LoadMember -> {
                    val (klass, param, arraySize) = getKlassParam(self)

                    listOfNotNull(
                        if (self.id != null) null
                        else ErrorInfo.StringWithSourceRef(self.sourceRef, "member ${self.name} not found"),

                        if (parent is Expression.ArrayLookup || parent is Expression.RawPointer || arraySize == null) null
                        else ErrorInfo.StringWithSourceRef(self.sourceRef, "member is an array")
                    )
                }

                else ->
                    listOf()
            }
        }
    }

    override fun scanFunction(self: Declaration.Function): List<ErrorInfo> {
        return super.scanFunction(self).ifEmpty {
            listOfNotNull(
                if (self.scope != Scope.Global || self.body != null || "extern" in self.attributes)
                    null
                else
                    ErrorInfo.StringWithSourceRef(self.sourceRef, "function declared without body"),

                if (self.body == null || self.returnType.isAssignableFrom(self.body.typeRef))
                    null
                else
                    ErrorInfo.StringWithSourceRef(self.sourceRef, "incompatible function return type and expression")
            )
        }
    }

    override fun scanLet(self: Declaration.Let): List<ErrorInfo> {
        return super.scanLet(self).ifEmpty {
            listOfNotNull(
                if (self.body == null || self.typeRef.isAssignableFrom(self.body.typeRef))
                    null
                else
                    ErrorInfo.StringWithSourceRef(self.sourceRef, "incompatible types between let and expression")
            )
        }
    }

    override fun scanKlass(self: Declaration.Klass): List<ErrorInfo> {
        return super.scanKlass(self).ifEmpty {
            // If there have been no errors in the inherited interfaces, check for correct function overrides etc
            if (self.extends.filterIsInstance<TypeRef.Klass>().any { scan(globals[it.id]).isNotEmpty() }) {
                listOf()
            } else {
                val members = self.flattenClassMembersBySignature { name, id -> globals[id]!! }

                members
                    // No ambiguity with duplicate inherited implementations
                    .filterValues { it.size > 1 }
                    .map { (key, list) ->
                        val func = list.first()
                        ErrorInfo.StringWithSourceRef(func.sourceRef, "Multiple implementations of ${func.name}")
                    } + if (self.isInterface) listOf() else
                // No unimplemented functions
                    members
                        .filterValues { it.first().body == null }
                        .map { (key, list) ->
                            val func = list.first()
                            ErrorInfo.StringWithSourceRef(func.sourceRef, "Unimplemented")
                        }
            }
        }
    }
}



fun inferTypesErrorScan(ast: Ast): List<ErrorInfo> {
    return InferTypesErrorScan(
        ast.declarations.flatMap { (_, declarations, _) -> declarations.map { tupleOf(it.id, it) } }.toMap(),
        ast.typeHints
    ).scan(ast)
}
