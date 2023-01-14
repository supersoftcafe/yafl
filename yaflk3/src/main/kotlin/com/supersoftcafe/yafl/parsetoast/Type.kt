package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
import com.supersoftcafe.yafl.ast.PrimitiveKind
import com.supersoftcafe.yafl.ast.TupleTypeField
import com.supersoftcafe.yafl.ast.TypeRef


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
        else -> throw IllegalArgumentException("Unknown primitive type $name")
    }
}

private fun YaflParser.TypePrimitiveContext.toTypeRef(): TypeRef.Primitive {
    return toPrimitiveTypeRef(NAME().text)
}

private fun YaflParser.TypeOfTupleContext.toTypeRef(): TypeRef {
    val type = TypeRef.Tuple(typeOfTuplePart().map {
        TupleTypeField(it.type().toTypeRef(), it.NAME()?.text)
    })

    return if (type.fields.size == 1 && type.fields[0].name == null) {
        type.fields[0].typeRef!!
    } else {
        type
    }
}

private fun YaflParser.TypeOfLambdaContext.toTypeRef(): TypeRef.Callable {
    val param = typeOfTuple().toTypeRef()
    return TypeRef.Callable(
        if (param is TypeRef.Tuple) param else TypeRef.Tuple(listOf(TupleTypeField(param, null))),
        type().toTypeRef()
    )
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
