package com.supersoftcafe.yafl.ast

import com.supersoftcafe.yafl.utils.Namer

sealed class TypeRef {
    abstract val resolved: Boolean      // Type might be incomplete, but all known parts are resolved
    abstract val complete: Boolean      // Type might have unresolved parts, but we do have all parts

    data class Array(val type: TypeRef?, val size: Long?) : TypeRef() {
        override val resolved = type?.resolved != false
        override val complete = type?.complete == true
    }

    data class Tuple(val fields: List<TupleTypeField>) : TypeRef() {
        override fun equals(other: Any?) = other is Tuple && fields == other.fields
        override fun hashCode() = fields.hashCode()
        override val resolved = fields.all { it.typeRef?.resolved != false }
        override val complete = fields.all { it.typeRef?.complete == true }
    }

    data class Callable(val parameter: TypeRef.Tuple?, val result: TypeRef?) : TypeRef() {
        override val resolved = parameter?.resolved != false && result?.resolved != false
        override val complete = parameter?.complete == true && result?.complete == true
    }

    data class Unresolved(val name: String, val id: Namer?) : TypeRef() {
        override val resolved = false
        override val complete = true
    }

    data class Named(val name: String, val id: Namer, val extends: List<TypeRef.Named>) : TypeRef() {
        override val resolved = true
        override val complete = true
    }

    data class Primitive(val kind: PrimitiveKind) : TypeRef() {
        override val resolved = true
        override val complete = true
    }

    object Unit : TypeRef() {
        override val resolved = true
        override val complete = true
    }

    companion object {
        val Bool = TypeRef.Primitive(PrimitiveKind.Bool)
        val Int8 = TypeRef.Primitive(PrimitiveKind.Int8)
        val Int16 = TypeRef.Primitive(PrimitiveKind.Int16)
        val Int32 = TypeRef.Primitive(PrimitiveKind.Int32)
        val Int64 = TypeRef.Primitive(PrimitiveKind.Int64)
        val Float32 = TypeRef.Primitive(PrimitiveKind.Float32)
        val Float64 = TypeRef.Primitive(PrimitiveKind.Float64)
    }
}
