package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.ast.PrimitiveKind
import com.supersoftcafe.yafl.ast.TupleTypeField
import com.supersoftcafe.yafl.ast.TypeRef


fun YaflParser.QualifiedNameContext.toName(): String {
    return NAMESPACE().joinToString("", "", NAME().text) { it.text }
}


private fun YaflParser.NamedTypeContext.toTypeRef(): TypeRef {
    return TypeRef.Unresolved(typeRef().qualifiedName().toName())
}

private fun YaflParser.PrimitiveTypeContext.toTypeRef(): TypeRef {
    return when (val name = typePrimitive().NAME().text) {
        "bool"    -> TypeRef.Primitive(PrimitiveKind.Bool)
        "int8"    -> TypeRef.Primitive(PrimitiveKind.Int8)
        "int16"   -> TypeRef.Primitive(PrimitiveKind.Int16)
        "int32"   -> TypeRef.Primitive(PrimitiveKind.Int32)
        "int64"   -> TypeRef.Primitive(PrimitiveKind.Int64)
        "float32" -> TypeRef.Primitive(PrimitiveKind.Float32)
        "float64" -> TypeRef.Primitive(PrimitiveKind.Float64)
        else -> throw IllegalArgumentException("Unknown primitive type $name")
    }
}

private fun YaflParser.TupleTypeContext.toTypeRef(): TypeRef {
    return TypeRef.Tuple(typeOfTuple().typeOfTuplePart().map {
        TupleTypeField(it.type().toTypeRef(), it.NAME()?.text)
    })
}

private fun YaflParser.LambdaTypeContext.toTypeRef(): TypeRef {
    TODO()
}

fun YaflParser.TypeContext.toTypeRef(): TypeRef {
    return when (this) {
        is YaflParser.NamedTypeContext -> toTypeRef()
        is YaflParser.PrimitiveTypeContext -> toTypeRef()
        is YaflParser.TupleTypeContext -> toTypeRef()
        is YaflParser.LambdaTypeContext -> toTypeRef()
        else -> throw IllegalArgumentException()
    }
}
