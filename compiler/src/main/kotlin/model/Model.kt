package model

import generator.FunctionBuilder
import generator.Operation
import generator.Register

const val WILDCARD = "_"

enum class Flags {

}

data class Root(val declarations: List<Declaration>, val realTypes: List<RealType> = emptyList())
enum class Operator { MULTIPLY, DIVIDE, MODULUS, ADD, SUBTRACT }
data class Parameter(val name: String, val type: Type?, val defaultValue: Expression?)
data class NamedParam(val name: String?, val value: Expression)

sealed class RealType {
    abstract val cname: String?

    data class Primitive(val fqn: String, override val cname: String? = null) : RealType()
    data class Structure(val fqn: String, override val cname: String? = null) : RealType()

}

sealed class Expression {
    abstract val type: Type?

    data class Named(val name: String, override val type: Type? = null) : Expression()
    data class IntLiteral(val value: Long, override val type: Type? = null) : Expression()
    data class Invoke(val target: Expression, val parameters: List<NamedParam>, override val type: Type? = null) : Expression()
    data class If(val condition: Expression, val left: CodeBlock, val right: CodeBlock, override val type: Type? = null) : Expression()
    data class Dot(val left: Expression, val right: String, override val type: Type? = null) : Expression()
    data class BinaryOp(val operator: Operator, val left: Expression, val right: Expression, override val type: Type? = null) : Expression()
    data class CodeBlock(val declarations: List<Declaration>, val expression: Expression, override val type: Type? = null) : Expression()
    // data class NewObject(val objectType: Type.Named, val functions: List<Declaration.Fun>) : Expression()
}

sealed class Type {
    abstract val realType: RealType?
    abstract val flags: Set<Flags>

    data class Named(val fqn: List<String>, override val realType: RealType? = null, override val flags: Set<Flags> = emptySet()) : Type()
    data class Tuple(val parts: List<Parameter>, override val realType: RealType? = null, override val flags: Set<Flags> = emptySet()) : Type()
    data class Function(val parameter: Tuple, val result: Type, override val realType: RealType? = null, override val flags: Set<Flags> = emptySet()) : Type()
}

object BuiltInTypes {
    val int = RealType.Primitive("int", "int32_t")
    val long = RealType.Primitive("long", "int64_t")
    val float = RealType.Primitive("float", "float")
    val double = RealType.Primitive("double", "double")
}

sealed class Declaration {
    abstract val name: String

    data class Let(override val name: String, val expression: Expression) : Declaration()

    data class Fun(override val name: String, val parameters: List<Parameter>, val type: Type?, val codeBlock: Expression.CodeBlock?) : Declaration()
//        override fun Emit(): String {
//            val fb = FunctionBuilder("fun_${name}", type?.cname!!)
//
//            for (param in parameter?.parts ?: emptyList())
//                fb.addRegister(param.type?.cname!!, isParameter = true)
//            val resultRegister = codeBlock!!.Emit(fb)
//            fb.addOperation(Operation.Return(resultRegister))
//
//            return fb.build()
//        }

    data class Data(override val name: String, val parameters: List<Parameter>) : Declaration()
    data class Class(override val name: String, val functions: List<Fun>) : Declaration()
}


