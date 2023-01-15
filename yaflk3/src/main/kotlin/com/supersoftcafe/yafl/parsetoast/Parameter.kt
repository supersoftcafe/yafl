package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.antlr.YaflParser
//import com.supersoftcafe.yafl.ast.Parameter

//fun YaflParser.UnpackTupleContext.toParameter(file: String, prefix: String = ""): Parameter.Tuple {
//    return Parameter.Tuple(null, unpackTuplePart().map { it.toParameter(file, prefix) })
//}
//
//fun YaflParser.UnpackTuplePartContext.toParameter(file: String, prefix: String = ""): Parameter {
//    return when (val upt = unpackTuple()) {
//        null -> Parameter.Value(type()?.toTypeRef(), prefix + NAME().text, expression()?.toExpression(file))
//        else -> upt.toParameter(file)
//    }
//}