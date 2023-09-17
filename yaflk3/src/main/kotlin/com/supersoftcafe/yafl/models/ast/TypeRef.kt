package com.supersoftcafe.yafl.models.ast

import com.supersoftcafe.yafl.utils.Namer

sealed class TypeRef {
    abstract val resolved: Boolean      // Type might be incomplete, but all known parts are resolved
    abstract val complete: Boolean      // Type might have unresolved parts, but we do have all parts

    data class Tuple(
        val fields: List<TupleTypeField>
    ) : TypeRef() {
        override fun equals(other: Any?) = other is Tuple && fields == other.fields
        override fun hashCode() = fields.hashCode()
        override val resolved = fields.all { it.typeRef?.resolved != false }
        override val complete = fields.all { it.typeRef?.complete == true }
    }

    data class TaggedValues(
        val tags: List<TagTypeField>
    ) : TypeRef() {
        init {
            // Check that everything maintains tag ordering
            assert(tags.map { it.name }.let { it == it.sorted() })
        }
        override fun equals(other: Any?) = other is TaggedValues && tags == other.tags
        override fun hashCode() = tags.hashCode()
        override val resolved = tags.all { it.typeRef.resolved != false }
        override val complete = tags.all { it.typeRef.complete == true }
    }

    data class Callable(
        val parameter: TypeRef?,
        val result: TypeRef?
    ) : TypeRef() {
        override val resolved = parameter?.resolved != false && result?.resolved != false
        override val complete = parameter?.complete == true && result?.complete == true
    }

    data class Unresolved(
        val name: String,
        val id: Namer?,
    ) : TypeRef() {
        override val resolved = false
        override val complete = true
    }

    data class Klass(
        val name: String,
        val id: Namer,
        val extends: List<Klass>,
    ) : TypeRef() {
        override val resolved = true
        override val complete = true
    }

    data class Primitive(val kind: PrimitiveKind) : TypeRef() {
        override val resolved = true
        override val complete = true
    }

//    object Unit : TypeRef() {
//        override val resolved = true
//        override val complete = true
//    }

    companion object {
        val Unit = Tuple(listOf())
        val Bool = Primitive(PrimitiveKind.Bool)
        val Int8 = Primitive(PrimitiveKind.Int8)
        val Int16 = Primitive(PrimitiveKind.Int16)
        val Int32 = Primitive(PrimitiveKind.Int32)
        val Int64 = Primitive(PrimitiveKind.Int64)
        val Float32 = Primitive(PrimitiveKind.Float32)
        val Float64 = Primitive(PrimitiveKind.Float64)
        val Pointer = Primitive(PrimitiveKind.Pointer)
        val Size = Primitive(PrimitiveKind.Size)
        val Int = Primitive(PrimitiveKind.Int)
    }
}
