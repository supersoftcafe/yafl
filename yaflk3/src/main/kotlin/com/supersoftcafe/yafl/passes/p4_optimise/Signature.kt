package com.supersoftcafe.yafl.passes.p4_optimise

import com.supersoftcafe.yafl.models.ast.TypeRef


fun TypeRef?.toSignature(): String? {
    return when (this) {
        is TypeRef.Callable -> {
            val result = result.toSignature()
            val param = parameter.toSignature()
            if (param != null && result != null)
                "$param:$result"
            else null
        }

        is TypeRef.TaggedValues -> {
            val types = tags.mapNotNull { tag -> tag.typeRef.toSignature()?.let { "|${tag.name}$it" } }
            if (types.size == tags.size)
                types.joinToString("")
            else null
        }

        is TypeRef.Tuple -> {
            val types = fields.mapNotNull { it.typeRef.toSignature() }
            if (types.size == fields.size)
                types.joinToString(",", "(", ")")
            else null
        }

        is TypeRef.Klass -> name
        is TypeRef.Primitive -> kind.fullyQualifiedName
        is TypeRef.Unresolved -> null
        null -> null
    }
}

fun TypeRef?.toSignature(name: String?): String? {
    return if (name != null)
        toSignature()?.let { "$name:$it" }
    else null
}
