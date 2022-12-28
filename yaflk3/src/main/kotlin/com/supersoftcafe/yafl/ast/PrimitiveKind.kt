package com.supersoftcafe.yafl.ast

enum class PrimitiveKind {
    Int8, Int16, Int32, Int64,
    Float32, Float64,
    Bool;

    val fullyQualifiedName = "System::$name"
}