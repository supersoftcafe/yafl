package com.supersoftcafe.yafl.ast

data class TupleTypeField(val typeRef: TypeRef?, val name: String?) {
    override fun equals(other: Any?) = other is TupleTypeField && typeRef == other.typeRef
    override fun hashCode() = typeRef.hashCode()
}
