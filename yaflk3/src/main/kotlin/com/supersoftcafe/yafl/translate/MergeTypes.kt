package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.TupleTypeField
import com.supersoftcafe.yafl.ast.TypeRef



fun TypeRef?.mightBeAssignableTo(receiver: TypeRef? ): Boolean {
    return if (receiver == null || this == null) {
        true
    } else when (this) {
        TypeRef.Unit ->
            receiver == this

        is TypeRef.Named ->
            (receiver as? TypeRef.Named)?.id == id || extends.any { it.mightBeAssignableTo(receiver) }

        is TypeRef.Primitive ->
            (receiver as? TypeRef.Primitive)?.kind == kind

        is TypeRef.Tuple ->
            fields.size == (receiver as? TypeRef.Tuple)?.fields?.size
                    && fields.zip(receiver.fields).all { (l, r) -> l.typeRef.mightBeAssignableTo(r.typeRef) }

        is TypeRef.Callable ->
            receiver is TypeRef.Callable
                    && result.mightBeAssignableTo(receiver.result)
                    && receiver.parameter.mightBeAssignableTo(parameter)

        is TypeRef.Unresolved ->
            throw IllegalStateException("TypeRef.Unresolved should not exist")
    }
}


fun TypeRef.Named.allAncestors(depth: Int): Map<TypeRef.Named, Int> {
    // Each ancestor is scored by its closest relationship to the root.
    return extends.fold(mapOf(this to depth)) { acc, parent ->
        (acc + parent.allAncestors(depth + 1)).mapValues { (key, value) ->
            // Take the smaller of the two values for any clashing key.
            acc.getOrDefault(key, value).coerceAtMost(value)
        }
    }
}

fun List<TypeRef.Named>.commonLeastDerivedAncestor(): TypeRef.Named? {
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


fun TypeRef?.isAssignableFrom(other: TypeRef?): Boolean {
    return if (this is TypeRef.Tuple && fields.size == 1) {
        fields[0].typeRef.isAssignableFrom(other)
    } else if (other is TypeRef.Tuple && other.fields.size == 1) {
        isAssignableFrom(other.fields[0].typeRef)
    } else when (this) {
        is TypeRef.Named -> other is TypeRef.Named && (other.id == id || other.extends.any { isAssignableFrom(it) })
        is TypeRef.Tuple -> other is TypeRef.Tuple && fields.size == other.fields.size && fields.zip(other.fields).all { (l, r) -> l.typeRef.isAssignableFrom(r.typeRef) }
        is TypeRef.Callable -> other is TypeRef.Callable && result.isAssignableFrom(other.result) && other.parameter.isAssignableFrom(parameter)
        is TypeRef.Primitive, TypeRef.Unit -> other == this
        is TypeRef.Unresolved, null -> false
    }
}

fun List<TypeRef.Named>.mostSpecificType(): TypeRef.Named? {
    return firstOrNull { source -> all { target -> target.isAssignableFrom(source) } }
}


fun mergeTypes(
    parsedType: TypeRef?,
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
    fun checkEverythingIs(predicate: (TypeRef)->Boolean) = inputTypes.all(predicate) && outputTypes.all(predicate)

    return when (parsedType) {
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
        TypeRef.Unit, is TypeRef.Named, is TypeRef.Primitive -> parsedType
        is TypeRef.Unresolved -> throw IllegalStateException("Unresolved")

        // Full inference. What are we dealing with?
        null ->
            when (val candidateType = inputTypes.firstOrNull() ?: outputTypes.firstOrNull()) {
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

                is TypeRef.Named ->
                    if (checkEverythingIs { it is TypeRef.Named }) {
                        outputTypes.filterIsInstance<TypeRef.Named>().mostSpecificType()
                            ?: inputTypes.filterIsInstance<TypeRef.Named>().commonLeastDerivedAncestor()
                    } else {
                        null
                    }

                is TypeRef.Primitive, TypeRef.Unit -> {
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