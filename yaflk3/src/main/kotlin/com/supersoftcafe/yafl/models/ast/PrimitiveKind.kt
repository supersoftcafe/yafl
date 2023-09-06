package com.supersoftcafe.yafl.models.ast

enum class PrimitiveKind(val fullyQualifiedName: String) {
    Bool("System::Bool"),
    Int8("System::Int8"),
    Int16("System::Int16"),
    Int32("System::Int32"),
    Int64("System::Int64"),
    Float32("System::Float32"),
    Float64("System::Float64"),

    Int("System::Interop::Int"),
    Size("System::Interop::Size"),
    Pointer("System::Interop::Pointer"),
    ;
}