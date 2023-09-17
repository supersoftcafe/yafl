package com.supersoftcafe.yafl.models.ast

data class TagTypeField(val typeRef: TypeRef.Tuple, val name: String) {
    override fun equals(other: Any?) = other is TagTypeField && name == other.name && typeRef == other.typeRef
    override fun hashCode() = typeRef.hashCode()
}
