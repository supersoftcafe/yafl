package com.supersoftcafe.yafl.passes.p3_infer

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.TagTypeField
import com.supersoftcafe.yafl.models.ast.TupleTypeField
import com.supersoftcafe.yafl.models.ast.TypeRef


fun TypeRef?.mightBeAssignableTo(receiver: TypeRef?): Boolean {
    return if (receiver == null || this == null) {
        true
    } else when (this) {
        TypeRef.Unit ->
            receiver == this

        is TypeRef.Klass ->
            ((receiver as? TypeRef.Klass)?.id == id) || extends.any { it.mightBeAssignableTo(receiver) }

        is TypeRef.TaggedValues ->
            (receiver as? TypeRef.TaggedValues)?.tags?.size == tags.size && tags.zip(receiver.tags)
                .all { (l, r) -> l.name == r.name && l.typeRef.mightBeAssignableTo(r.typeRef) }

        is TypeRef.Primitive ->
            (receiver as? TypeRef.Primitive)?.kind == kind

        is TypeRef.Tuple ->
            fields.size == (receiver as? TypeRef.Tuple)?.fields?.size &&
                    fields.zip(receiver.fields).all { (l, r) -> l.typeRef.mightBeAssignableTo(r.typeRef) }

        is TypeRef.Callable ->
            receiver is TypeRef.Callable
                    && result.mightBeAssignableTo(receiver.result)
                    && receiver.parameter.mightBeAssignableTo(parameter)

        is TypeRef.Unresolved ->
            throw IllegalStateException("TypeRef.Unresolved should not exist")
    }
}


fun TypeRef.Klass.allAncestors(depth: Int): Map<TypeRef.Klass, Int> {
    // Each ancestor is scored by its closest relationship to the root.
    return extends.fold(mapOf(this to depth)) { acc, parent ->
        (acc + parent.allAncestors(depth + 1)).mapValues { (key, value) ->
            // Take the smaller of the two values for any clashing key.
            acc.getOrDefault(key, value).coerceAtMost(value)
        }
    }
}

fun TypeRef?.isAssignableFrom(other: TypeRef?): Boolean {
    return if (this is TypeRef.Tuple && fields.size == 1) {
        fields[0].typeRef.isAssignableFrom(other)

    } else if (other is TypeRef.Tuple && other.fields.size == 1) {
        isAssignableFrom(other.fields[0].typeRef)

    } else when (this) {
        is TypeRef.Klass ->
            other is TypeRef.Klass && ((other.id == id)|| other.extends.any { isAssignableFrom(it) })

        is TypeRef.Tuple ->
            // TODO: If dst.size >= src.size && src.size >= 1 (so no Unit) && all src[n] are assignable to a single unambiguous target slot, even if that means loosing positional information
            other is TypeRef.Tuple && fields.size == other.fields.size &&
                    fields.zip(other.fields).all { (l, r) -> l.typeRef.isAssignableFrom(r.typeRef) }

        is TypeRef.TaggedValues ->
            (other as? TypeRef.TaggedValues)?.tags?.size == tags.size && tags.zip(other.tags)
                .all { (l, r) -> l.name == r.name && l.typeRef.isAssignableFrom(r.typeRef) }

        is TypeRef.Callable ->
            other is TypeRef.Callable && result.isAssignableFrom(other.result) && other.parameter.isAssignableFrom(parameter)

        is TypeRef.Primitive ->
            other == this

        is TypeRef.Unresolved, null ->
            false
    }
}

fun TypeRef?.isAssignableFrom(other: Declaration.Klass): Boolean {
    return this is TypeRef.Klass && (id == other.id || other.extends.any { isAssignableFrom(it) })
}

fun List<TypeRef.Klass>.commonLeastDerivedAncestor(): TypeRef.Klass? {
    // Find only the keys common between each ancestor map.
    val ancestors = map { it.allAncestors(0) }.reduce { map1, map2 ->
        map1.keys.intersect(map2.keys).associateWith { key ->
            // Take the smaller of the two values for any clashing key.
            map1.getOrDefault(key, Int.MAX_VALUE).coerceAtMost(map2.getOrDefault(key, Int.MAX_VALUE))
        }
    }
    return ancestors.values.minOrNull()?.let { minDepth ->
        // Find the candidate with the lowest depth, but only if there are no others with the same depth.
        ancestors.filter { (_, depth) -> depth == minDepth }.toList().singleOrNull()?.first
    }
}

fun TypeRef?.toArrayInitializer(dimensions: Int): TypeRef.Callable {
    return TypeRef.Callable(TypeRef.Tuple(List(dimensions) { TupleTypeField(TypeRef.Int32, null) }), this)
}

fun List<TypeRef.Klass>.mostSpecificType(): TypeRef.Klass? {
    return firstOrNull { source -> all { target -> target.isAssignableFrom(source) } }
}


fun mergeTypes(
    parsedType: TypeRef? = null,
    inputType: TypeRef? = null,
    outputType: TypeRef? = null
): TypeRef? {
    return mergeTypes(parsedType, listOfNotNull(inputType), listOfNotNull(outputType))
}

fun mergeTypes(
    parsedType: TypeRef?,
    inputTypes: List<TypeRef> = listOf(),
    outputTypes: List<TypeRef> = listOf()
): TypeRef? {
    fun checkEverythingIs(predicate: (TypeRef)->Boolean) =
        inputTypes.all(predicate) && outputTypes.all(predicate)
    fun List<TypeRef>.getTagFieldTypes(name: String) =
        mapNotNull { (it as? TypeRef.TaggedValues)?.tags?.firstOrNull { it.name == name }?.typeRef }
    fun List<TypeRef>.getTagFieldNames() =
        flatMap { (it as? TypeRef.TaggedValues)?.tags?.map { it.name } ?: listOf() }.toSet()

    return when (parsedType) {
        is TypeRef.TaggedValues -> {
            if (checkEverythingIs { it is TypeRef.TaggedValues }) {
                parsedType.copy(tags = parsedType.tags.map { tag ->
                    tag.copy(
                        typeRef = mergeTypes(
                            tag.typeRef,
                            inputTypes .getTagFieldTypes(tag.name),
                            outputTypes.getTagFieldTypes(tag.name)
                        ) as? TypeRef.Tuple ?: tag.typeRef
                    )
                })
            } else {
                parsedType
            }
        }

        // If the original code specifies a tuple, we need to see what parts are well-defined and keep those.
        // However, the parts that are not well-defined can be inferred.
        is TypeRef.Tuple ->
            // Recurse into members
            if (checkEverythingIs { it is TypeRef.Tuple && it.fields.size == parsedType.fields.size }) {
                parsedType.copy(fields = parsedType.fields.mapIndexed { index, field ->
                    field.copy(typeRef = mergeTypes(
                        field.typeRef,
                        inputTypes .mapNotNull { (it as? TypeRef.Tuple)?.fields?.get(index)?.typeRef },
                        outputTypes.mapNotNull { (it as? TypeRef.Tuple)?.fields?.get(index)?.typeRef }
                    ))
                })
            } else {
                parsedType
            }

        // If the original code specifies a callable, we need to see what parts are well-defined and keep those.
        // However, the parts that are not well-defined can be inferred.
        is TypeRef.Callable ->
            // Recurse into members. Swap input/output for parameter.
            if (checkEverythingIs { it is TypeRef.Callable }) {
                parsedType.copy(
                    result = mergeTypes(
                        parsedType.result,
                        inputTypes .mapNotNull { (it as? TypeRef.Callable)?.result },
                        outputTypes.mapNotNull { (it as? TypeRef.Callable)?.result },
                    ),
                    parameter = mergeTypes(
                        parsedType.parameter,
                        outputTypes.mapNotNull { (it as? TypeRef.Callable)?.parameter },
                        inputTypes .mapNotNull { (it as? TypeRef.Callable)?.parameter },
                    ) as? TypeRef.Tuple
                )
            } else {
                parsedType
            }

        // All fully resolved types are unchanged if clearly specified by the original code.
        is TypeRef.Klass, is TypeRef.Primitive ->
            parsedType

        is TypeRef.Unresolved ->
            throw IllegalStateException("Unresolved")

        // Full inference. What are we dealing with?
        null ->
            when (val candidateType = inputTypes.firstOrNull() ?: outputTypes.firstOrNull()) {
                is TypeRef.TaggedValues -> {
                    if (checkEverythingIs { it is TypeRef.Tuple }) {
                        val names = inputTypes.getTagFieldNames() + outputTypes.getTagFieldNames()
                        TypeRef.TaggedValues(tags = names.mapNotNull { name ->
                            (mergeTypes(
                                null,
                                inputTypes .getTagFieldTypes(name),
                                outputTypes.getTagFieldTypes(name)
                            ) as? TypeRef.Tuple)?.let {
                                TagTypeField(it, name)
                            }
                        }.sortedBy { it.name })
                    } else {
                        null
                    }
                }

                is TypeRef.Tuple -> {
                    if (checkEverythingIs { it is TypeRef.Tuple && it.fields.size == candidateType.fields.size }) {
                        TypeRef.Tuple(
                            fields = List(candidateType.fields.size) { index ->
                                TupleTypeField(
                                    name = inputTypes.mapNotNull {
                                        (it as? TypeRef.Tuple)?.fields?.get(index)?.name
                                    }.distinct().singleOrNull(),
                                    typeRef = mergeTypes(
                                        null,
                                        inputTypes .mapNotNull { (it as? TypeRef.Tuple)?.fields?.get(index)?.typeRef },
                                        outputTypes.mapNotNull { (it as? TypeRef.Tuple)?.fields?.get(index)?.typeRef }
                                    )
                                )
                            }
                        )
                    } else {
                        null
                    }
                }

                is TypeRef.Callable -> {
                    if (checkEverythingIs { it is TypeRef.Callable }) {
                        TypeRef.Callable(
                            result = mergeTypes(
                                null,
                                inputTypes .mapNotNull { (it as? TypeRef.Callable)?.result },
                                outputTypes.mapNotNull { (it as? TypeRef.Callable)?.result },
                            ),
                            parameter = mergeTypes(
                                null, // Swap in/out as we recurse into callable parameters
                                outputTypes.mapNotNull { (it as? TypeRef.Callable)?.parameter },
                                inputTypes .mapNotNull { (it as? TypeRef.Callable)?.parameter },
                            ) as? TypeRef.Tuple
                        )
                    } else {
                        null
                    }
                }

                is TypeRef.Klass ->
                    if (checkEverythingIs { it is TypeRef.Klass }) {
                        outputTypes.filterIsInstance<TypeRef.Klass>().mostSpecificType()
                            ?: inputTypes.filterIsInstance<TypeRef.Klass>().commonLeastDerivedAncestor()
                    } else {
                        null
                    }

                is TypeRef.Primitive -> {
                    // There are no implicit conversions on primitives. Check that all input and output are the same
                    if (checkEverythingIs { it == candidateType }) {
                        candidateType
                    } else {
                        null
                    }
                }

                is TypeRef.Unresolved ->
                    throw IllegalStateException("Unresolved")

                // There really is nothing to infer from
                null -> null
            }
    }
}