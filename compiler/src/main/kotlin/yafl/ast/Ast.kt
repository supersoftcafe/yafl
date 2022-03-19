package yafl.ast

data class AstProject(var modules: MutableMap<String, AstModule>)
data class DeclareField(var name: String, var type: Type? = null)
data class InvokeParameter(var name: String?, var value: Expression)

data class AstModule(
    var name: String,
    var imports: MutableList<String> = mutableListOf(),
    var declarations: MutableMap<String, Declaration> = mutableMapOf()
)

sealed class Declaration {
    abstract var name: String

    data class Var(
        override var name: String,
        var expression: Expression,
        var type: Type? = null
    ) : Declaration()

    data class Fun(
        override var name: String,
        var expression: Expression?,
        var params: Type.Tuple,
        var type: Type? = null
    ) : Declaration()

    data class Struct(
        override var name: String,
        var fields: MutableList<DeclareField>
    ) : Declaration()
}

sealed class Type {
    // Tuple fields always have a name, either implicit 'Field1' etc or explicit in code
    data class Tuple(var fields: List<DeclareField>) : Type()
    data class Named(var name: String, var genericParams: List<Type>) : Type()
}



sealed class Expression {
    var type: Type? = null
    var line: Int? = null
    var file: String? = null
    var declarations: MutableMap<String, Declaration>? = mutableMapOf()

    sealed class Literal : Expression() {
        data class Int8(var value: Byte) : Literal()
        data class Int16(var value: Short) : Literal()
        data class Int32(var value: Int) : Literal()
        data class Int64(var value: Long) : Literal()
        data class Float32(var value: Float) : Literal()
        data class Float64(var value: Double) : Literal()
        data class LString(var value: String) : Literal()
    }
    sealed class Operator : Expression() {
        data class NamedThing(var name: String) : Operator()
        data class Dot(var left: Expression, var right: String) : Operator()
        data class Plus(var left: Expression, var right: Expression) : Operator()
        data class Divide(var left: Expression, var right: Expression) : Operator()
        data class Multiply(var left: Expression, var right: Expression) : Operator()
        data class Remainder(var left: Expression, var right: Expression) : Operator()
        data class Minus(var left: Expression, var right: Expression) : Operator()
        data class UnaryMinus(var value: Expression) : Operator()
    }
    sealed class Memory : Expression() {
        data class Invoke(var reference: Reference, var parameters: List<InvokeParameter>, var mustTail: Boolean = false) : Control()
        data class Load(var reference: Reference) : Memory()
        data class Store(var reference: Reference, var expr: Expression) : Memory()
    }
    sealed class Control : Expression() {
        data class If(var condition: Expression, var left: Expression, var right: Expression) : Control()
    }
}

sealed class Reference {
    data class Unknown(var name: String) : Reference()
    data class Local(var name: String) : Reference()
    data class Global(var name: String) : Reference()
    data class Field(var left: Expression, var right: String) : Reference()
    data class Array(var left: Expression, var right: Expression) : Reference()
}




