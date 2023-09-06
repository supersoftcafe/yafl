package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.Declaration
import com.supersoftcafe.yafl.models.ast.TypeRef
import com.supersoftcafe.yafl.models.llir.CgType
import com.supersoftcafe.yafl.models.llir.CgTypePrimitive
import com.supersoftcafe.yafl.models.llir.CgTypeStruct


fun Declaration.Type.toCgType(globals: Globals): CgType = when (this) {
    is Declaration.Alias   -> throw IllegalStateException("Dangling alias")
    is Declaration.Klass   -> CgTypePrimitive.OBJECT
    is Declaration.Enum    -> toCgTypeEnum(globals)
}

fun TypeRef.Tuple.toCgType(globals: Globals) =
    CgTypeStruct(fields.map { it.typeRef.toCgType(globals) })

fun TypeRef.Primitive.toCgType() = when (kind) {
    com.supersoftcafe.yafl.models.ast.PrimitiveKind.Bool    -> CgTypePrimitive.BOOL
    com.supersoftcafe.yafl.models.ast.PrimitiveKind.Int8    -> CgTypePrimitive.INT8
    com.supersoftcafe.yafl.models.ast.PrimitiveKind.Int16   -> CgTypePrimitive.INT16
    com.supersoftcafe.yafl.models.ast.PrimitiveKind.Int32   -> CgTypePrimitive.INT32
    com.supersoftcafe.yafl.models.ast.PrimitiveKind.Int64   -> CgTypePrimitive.INT64
    com.supersoftcafe.yafl.models.ast.PrimitiveKind.Float32 -> CgTypePrimitive.FLOAT32
    com.supersoftcafe.yafl.models.ast.PrimitiveKind.Float64 -> CgTypePrimitive.FLOAT64

    com.supersoftcafe.yafl.models.ast.PrimitiveKind.Int     -> CgTypePrimitive.INT
    com.supersoftcafe.yafl.models.ast.PrimitiveKind.Size    -> CgTypePrimitive.SIZE
    com.supersoftcafe.yafl.models.ast.PrimitiveKind.Pointer -> CgTypePrimitive.POINTER
}

fun TypeRef?.toCgType(globals: Globals): CgType {
    return when (this) {
        null ->
            throw IllegalStateException("Danging null TypeRef")

        TypeRef.Unit ->
            CgTypePrimitive.OBJECT

        is TypeRef.Unresolved ->
            throw IllegalStateException("Dangling unresolved TypeRef")

        is TypeRef.Enum -> {
            val x = globals.type[id] ?: throw IllegalStateException("Type lookup failure")
            x.toCgType(globals)
        }

        is TypeRef.Klass -> {
            val x = globals.type[id] ?: throw IllegalStateException("Type lookup failure")
            x.toCgType(globals)
        }

        is TypeRef.Callable ->
            CgTypeStruct.functionPointer

        is TypeRef.Tuple ->
            toCgType(globals)

        is TypeRef.Primitive ->
            toCgType()
    }
}
