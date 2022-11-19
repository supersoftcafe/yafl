package com.supersoftcafe.yafl.ast

data class TypeHints(val lookup: Map<Long,List<TypeHint>> = mapOf()) {
    operator fun get(id: Long) = lookup[id] ?: listOf()
    fun getTypeRefs(id: Long) = get(id).map { it.typeRef }
    operator fun plus(other: TypeHints) =
        TypeHints(lookup.keys.union(other.lookup.keys).associateWith { get(it).union(other[it]).toList() } )
}

private val EMPTY_TYPE_HINTS = TypeHints()
fun emptyTypeHints() = EMPTY_TYPE_HINTS
fun typeHintsOf(hint: Pair<Long, TypeHint>) = TypeHints(mapOf(hint.first to listOf(hint.second)))