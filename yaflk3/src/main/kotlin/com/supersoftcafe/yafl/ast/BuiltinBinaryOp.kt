package com.supersoftcafe.yafl.ast

enum class BuiltinBinaryOp(val ltype: TypeRef, val rtype: TypeRef) {
    ADD_I32(TypeRef.Primitive(PrimitiveKind.Int32), TypeRef.Primitive(PrimitiveKind.Int32)),
    ADD_I64(TypeRef.Primitive(PrimitiveKind.Int64), TypeRef.Primitive(PrimitiveKind.Int64)),
    SUB_I32(TypeRef.Primitive(PrimitiveKind.Int32), TypeRef.Primitive(PrimitiveKind.Int32)),
    MUL_I32(TypeRef.Primitive(PrimitiveKind.Int32), TypeRef.Primitive(PrimitiveKind.Int32)),
    DIV_I32(TypeRef.Primitive(PrimitiveKind.Int32), TypeRef.Primitive(PrimitiveKind.Int32)),
    REM_I32(TypeRef.Primitive(PrimitiveKind.Int32), TypeRef.Primitive(PrimitiveKind.Int32)),
    EQU_I32(TypeRef.Primitive(PrimitiveKind.Int32), TypeRef.Primitive(PrimitiveKind.Int32)),
     LT_I32(TypeRef.Primitive(PrimitiveKind.Int32), TypeRef.Primitive(PrimitiveKind.Int32)),
}
