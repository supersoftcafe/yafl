package com.supersoftcafe.yafl.ast

sealed class TypeRef {
    abstract val resolved: Boolean      // Type might be incomplete, but all known parts are resolved
    abstract val complete: Boolean      // Type might have unresolved parts, but we do have all parts

    data class Tuple(val fields: List<TupleTypeField>) : TypeRef() {
        override fun equals(other: Any?) = other is Tuple && fields == other.fields;
        override fun hashCode() = fields.hashCode()
        override val resolved = fields.all { it.typeRef?.resolved != false }
        override val complete = fields.all { it.typeRef?.complete == true }
    }

    data class Callable(val parameter: TypeRef.Tuple?, val result: TypeRef?) : TypeRef() {
        override val resolved = parameter?.resolved != false && result?.resolved != false
        override val complete = parameter?.complete == true && result?.complete == true
    }

    data class Unresolved(val name: String) : TypeRef() {
        override val resolved = false
        override val complete = true
    }

    data class Named(val name: String, val id: Long) : TypeRef() {
        override val resolved = true
        override val complete = true
    }

    data class Primitive(val kind: PrimitiveKind) : TypeRef() {
        override val resolved = true
        override val complete = true
    }
}
