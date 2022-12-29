package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.ast.PrimitiveKind
import com.supersoftcafe.yafl.ast.TupleTypeField
import com.supersoftcafe.yafl.ast.TypeRef


fun YaflParser.QualifiedNameContext.toName(): String {
    return NAMESPACE().joinToString("", "", NAME().text) { it.text }
}


fun YaflParser.TypeRefContext.toTypeRef(): TypeRef.Unresolved {
    return TypeRef.Unresolved(qualifiedName().toName(), null)
}

private fun YaflParser.TypePrimitiveContext.toTypeRef(): TypeRef.Primitive {
    return when (val name = NAME().text) {
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

private fun YaflParser.TypeOfTupleContext.toTypeRef(): TypeRef.Tuple {
    return TypeRef.Tuple(typeOfTuplePart().map {
        TupleTypeField(it.type().toTypeRef(), it.NAME()?.text)
    })
}

private fun YaflParser.TypeOfLambdaContext.toTypeRef(): TypeRef.Callable {
    TODO()
}

fun YaflParser.TypeContext.toTypeRef(): TypeRef {
    return when (this) {
        is YaflParser.NamedTypeContext -> typeRef().toTypeRef()
        is YaflParser.PrimitiveTypeContext -> typePrimitive().toTypeRef()
        is YaflParser.TupleTypeContext -> typeOfTuple().toTypeRef()
        is YaflParser.LambdaTypeContext -> typeOfLambda().toTypeRef()
        else -> throw IllegalArgumentException()
    }
}
