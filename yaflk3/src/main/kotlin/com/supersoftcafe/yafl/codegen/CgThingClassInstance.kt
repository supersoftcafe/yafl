package com.supersoftcafe.yafl.codegen

data class CgThingClassInstance(
    val name: String,
    val className: String,
    val fieldValues: List<*>,
) : CgThing {

    private fun Any.toContent(): Pair<String, String> {
        return when (this) {
            is Byte  ->  "i8" to toString()
            is Short -> "i16" to toString()
            is Int   -> "i32" to toString()
            is Long  -> "i64" to toString()
            is ByteArray  -> "[ $size x i8 ]"  to joinToString(",", "[", " ]") { " i8 $it" }
            is ShortArray -> "[ $size x i16 ]" to joinToString(",", "[", " ]") { " i16 $it" }
            is IntArray   -> "[ $size x i32 ]" to joinToString(",", "[", " ]") { " i32 $it" }
            is LongArray  -> "[ $size x i64 ]" to joinToString(",", "[", " ]") { " i64 $it" }
            is List<*> -> {
                val results = map { it!!.toContent() }
                results.joinToString(", ", "{ ", " }") { (type, value) -> type } to
                    results.joinToString(", ", "{ ", " }") { (type, value) -> "$type $value" }
            }
            else -> throw IllegalArgumentException("Unsupported type for static class instance")
        }
    }

    fun toIr(context: CgContext): CgLlvmIr {
        val classInfo = CgClassInfo(className)

        val (contentType, contentData) = fieldValues.toContent()
        val fullType = "{ %object, $contentType }"

        return CgLlvmIr(declarations =
            "@\"$name.obj\" = internal constant $fullType { %object { %vtable* bitcast( ${classInfo.vtableTypeName}* ${classInfo.vtableDataName} to %vtable*), %size_t 0 }, $contentType $contentData }\n" +
            "@\"$name\" = internal constant %object* bitcast($fullType* @\"$name.obj\" to %object*)\n")
    }
}