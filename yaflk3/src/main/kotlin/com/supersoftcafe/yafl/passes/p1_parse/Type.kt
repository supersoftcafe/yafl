package com.supersoftcafe.yafl.passes.p1_parse

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.models.ast.TagTypeField
import com.supersoftcafe.yafl.models.ast.TupleTypeField
import com.supersoftcafe.yafl.models.ast.TypeRef



fun YaflParser.QualifiedNameContext.toName(): String {
    return NAME().joinToString("::")
}

fun YaflParser.TypeRefContext.toTypeRef(): TypeRef.Unresolved {
    return TypeRef.Unresolved(qualifiedName().toName(), null)
}

private fun toPrimitiveTypeRef(name: String): TypeRef.Primitive {
    return when (name) {
        "bool"    -> TypeRef.Bool
        "int8"    -> TypeRef.Int8
        "int16"   -> TypeRef.Int16
        "int32"   -> TypeRef.Int32
        "int64"   -> TypeRef.Int64
        "float32" -> TypeRef.Float32
        "float64" -> TypeRef.Float64
        "pointer" -> TypeRef.Pointer
        "size"    -> TypeRef.Size
        "int"     -> TypeRef.Int
        else -> throw IllegalArgumentException("Unknown primitive type $name")
    }
}

private fun YaflParser.TypePrimitiveContext.toTypeRef(): TypeRef.Primitive {
    return toPrimitiveTypeRef(NAME().text)
}


fun YaflParser.TypeOfTupleContext.toTypeRef(): TypeRef.Tuple {
    return TypeRef.Tuple(typeOfTuplePart().map {
        TupleTypeField(it.type().toTypeRef(), it.NAME()?.text)
    })
}

fun YaflParser.TypeOfTagsContext.toTypeRef(): TypeRef.TaggedValues {
    return TypeRef.TaggedValues(typeOfTagsPart().map {
        TagTypeField(it.typeOfTuple()?.toTypeRef() ?: TypeRef.Unit, it.TAG().text)
    })
}

private fun YaflParser.TypeOfLambdaContext.toTypeRef(): TypeRef.Callable {
    return TypeRef.Callable(typeOfTuple().toTypeRef(), type().toTypeRef())
}

fun YaflParser.TypeContext.toTypeRef(): TypeRef {
    return when (this) {
        is YaflParser.NamedTypeContext     -> typeRef(      ).toTypeRef()
        is YaflParser.PrimitiveTypeContext -> typePrimitive().toTypeRef()
        is YaflParser.TupleTypeContext     -> typeOfTuple(  ).toTypeRef()
        is YaflParser.TagsTypeContext      -> typeOfTags(   ).toTypeRef()
        is YaflParser.LambdaTypeContext    -> typeOfLambda( ).toTypeRef()
        else -> throw IllegalArgumentException()
    }
}
