package com.supersoftcafe.yaflc.asttoir

import com.supersoftcafe.yaflc.Declaration
import com.supersoftcafe.yaflc.Field
import com.supersoftcafe.yaflc.PrimitiveKind
import com.supersoftcafe.yaflc.Type
import com.supersoftcafe.yaflc.codegen.CgType
import com.supersoftcafe.yaflc.codegen.CgTypePrimitive
import com.supersoftcafe.yaflc.codegen.CgTypeStruct


private fun List<Field>.toCgType(): CgType {
    return CgTypeStruct(map { it.type!!.toCgType() })
}

fun Type.toCgType(): CgType {
    return when (this) {
        is Type.Named -> when (val decl = declaration!!) {
            is Declaration.Primitive -> when (decl.kind) {
                PrimitiveKind.Bool -> CgTypePrimitive.BOOL
                PrimitiveKind.Int8 -> CgTypePrimitive.INT8
                PrimitiveKind.Int16 -> CgTypePrimitive.INT16
                PrimitiveKind.Int32 -> CgTypePrimitive.INT32
                PrimitiveKind.Int64 -> CgTypePrimitive.INT64
                PrimitiveKind.Float32 -> CgTypePrimitive.FLOAT32
                PrimitiveKind.Float64 -> CgTypePrimitive.FLOAT64
            }
            is Declaration.Struct -> if (decl.onHeap) {
                CgTypePrimitive.OBJECT
            } else {
                decl.fields.toCgType()
            }
            else -> throw IllegalArgumentException()
        }
        is Type.Function -> CgTypePrimitive.CALLABLE
        is Type.Tuple -> fields.toCgType()
    }
}
