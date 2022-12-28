package com.supersoftcafe.yafl.ast

import com.supersoftcafe.yafl.utils.Namer

data class TypeHints(val lookup: Map<Namer,List<TypeHint>> = mapOf()) {
    operator fun get(id: Namer) = lookup[id] ?: listOf()
    fun getInputTypeRefs (id: Namer) = get(id).mapNotNull { it.inputTypeRef }
    fun getOutputTypeRefs(id: Namer) = get(id).mapNotNull { it.outputTypeRef }
    operator fun plus(other: TypeHints) =
        TypeHints(lookup.keys.union(other.lookup.keys).associateWith { get(it).union(other[it]).toList() } )
}

private val EMPTY_TYPE_HINTS = TypeHints()
fun emptyTypeHints() = EMPTY_TYPE_HINTS
fun typeHintsOf(hint: Pair<Namer, TypeHint>) = TypeHints(mapOf(hint.first to listOf(hint.second)))
fun typeHintsOf(hints: List<Pair<Namer, TypeHint>>) = TypeHints(hints.associate { (name, hint) -> name to listOf(hint) })
