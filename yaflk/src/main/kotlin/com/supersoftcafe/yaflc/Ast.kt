package com.supersoftcafe.yaflc


sealed interface INode

class Field(val name: String, var type: Type?, val sourceRef: SourceRef) {
    override fun equals(other: Any?): Boolean {
        return other is Field && type == other.type
    }

    override fun hashCode(): Int {
        return type.hashCode()
    }
}

enum class PrimitiveKind(val irType: String) {
    Bool("b"),
    Int8("i1"),
    Int16("i2"),
    Int32("i4"),
    Int64("i8"),
    Float32("f4"),
    Float64("f8")
}

sealed class Declaration(
    val name: String,
    val sourceRef: SourceRef,
    var type: Type?
) : INode {
    val stuff = mutableListOf<Any>()

    class Struct(
        name: String,
        val fields: List<Field>,
        sourceRef: SourceRef,
        type: Type? = null
    ) : Declaration(name, sourceRef, type)

    class Primitive(
        name: String,
        val kind: PrimitiveKind,
        sourceRef: SourceRef,
        type: Type? = null
    ) : Declaration(name, sourceRef, type)

    class Variable(
        name: String,
        val body: ExpressionRef?,
        type: Type? = null,
        sourceRef: SourceRef,
        val global: Boolean = false
    ) : Declaration(name, sourceRef, type)

    class Function(
        name: String,
        val parameters: List<Variable>,
        var result: Type?,
        val body: ExpressionRef,
        type: Type? = null,
        sourceRef: SourceRef,
        val synthetic: Boolean = false
    ) : Declaration(name, sourceRef, type)
}

open class ExpressionRef(var expression: Expression, var receiver: Type?)
class TupleField(val name: String?, expression: Expression, receiver: Type?) : ExpressionRef(expression, receiver)

sealed class Expression(val sourceRef: SourceRef, var type: Type?) : INode {
    val stuff = mutableListOf<Any>()

    val children: MutableList<ExpressionRef> = mutableListOf()
    fun addChild(expr: Expression?, type: Type? = null) {
        if (expr != null)
            children.add(ExpressionRef(expr, type))
    }

    class LiteralBool(val value: Boolean, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type)
    class LiteralFloat(val value: Double, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type)
    class LiteralInteger(val value: Long, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type)
    class LiteralString(val value: String, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type)
    class LoadVariable(val name: String, var variable: Declaration? = null, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type)
    class LoadBuiltin(val name: String, sourceRef: SourceRef, type: Type? = null, var builtinOp: BuiltinOp? = null) : Expression(sourceRef, type)

    class LoadField(val name: String, base: Expression, var field: Field? = null, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type) {
        init { addChild(base, type) }
    }

    class Lambda(val parameters: List<Declaration.Variable>, var result: Type?, body: Expression?, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type) {
        init { addChild(body, (type as? Type.Function)?.result) }
    }

    class Call(target: Expression, parameter: Tuple, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type) {
        init {
            addChild(target)
            addChild(parameter)
        }
    }

    class Condition(check: Expression, ifTrue: Expression, ifFalse: Expression, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type) {
        init {
            addChild(check)
            addChild(ifTrue)
            addChild(ifFalse)
        }
    }

    class StoreVariable(val name: String, val variable: Declaration.Variable? = null, init: Expression, tail: Expression, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type) {
        init {
            addChild(init)
            addChild(tail)
        }
    }

    class DeclareLocal(val declarations: List<Declaration>, tail: Expression, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type) {
        init {
            for (declaration in declarations) {
                when (declaration) {
                    is Declaration.Variable -> children.add(declaration.body!!)
                    is Declaration.Function -> children.add(declaration.body)
                    else -> throw IllegalArgumentException("${declaration::class.simpleName} cannot be declared in a local context")
                }
            }
            addChild(tail)
        }
    }

    class Tuple(fields: List<TupleField>, sourceRef: SourceRef, type: Type? = null) : Expression(sourceRef, type) {
        init { children.addAll(fields) }
    }
}

sealed class Type(val sourceRef: SourceRef) {
    class Named(val typeName: String, sourceRef: SourceRef, val moduleName: String? = null, var declaration: Declaration? = null) : Type(sourceRef) {
        override fun equals(other: Any?) = other is Named && declaration != null && declaration === other.declaration
        override fun hashCode() = declaration?.hashCode() ?: 0
    }

    class Tuple(val fields: List<Field>, sourceRef: SourceRef) : Type(sourceRef) {
        override fun equals(other: Any?) = other is Tuple && fields == other.fields
        override fun hashCode() = fields.hashCode()
    }

    class Function(val parameter: Tuple, var result: Type?, sourceRef: SourceRef) : Type(sourceRef) {
        override fun equals(other: Any?) = other is Function && parameter == other.parameter && result == other.result
        override fun hashCode() = 31 * parameter.hashCode() + result.hashCode()
    }
}

class ModulePart(val imports: List<Module>, val module: Module) : INode {
    init {
        module.parts.add(this)
    }
    val declarations = mutableListOf<Declaration>()
}

class Module(val name: String) {
    val parts = mutableListOf<ModulePart>()
}

enum class BuiltinOpKind {
    CONVERT_I8_to_I16, CONVERT_I16_TO_I32, CONVERT_I32_TO_I64, CONVERT_F32_TO_F64,
    ADD_I8, ADD_I16, ADD_I32, ADD_I64, ADD_F32, ADD_F64;
}

class BuiltinOp(val name: String, val parameter: Type.Tuple, val result: Type, val kind: BuiltinOpKind)

class Ast {
    val systemModule = Module("System")
    val systemModulePart = ModulePart(mutableListOf(systemModule), systemModule)

    val syntheticModule = Module("^Synthetic")
    val syntheticModulePart = ModulePart(mutableListOf(systemModule, syntheticModule), syntheticModule)

    val modules = mutableListOf(systemModule, syntheticModule)


    val typeBool = createPrimitive("Bool", PrimitiveKind.Bool)
    val typeInt8 = createPrimitive("Int8", PrimitiveKind.Int8)
    val typeInt16 = createPrimitive("Int16", PrimitiveKind.Int16)
    val typeInt32 = createPrimitive("Int32", PrimitiveKind.Int32)
    val typeInt64 = createPrimitive("Int64", PrimitiveKind.Int64)
    val typeFloat32 = createPrimitive("Float32", PrimitiveKind.Float32)
    val typeFloat64 = createPrimitive("Float64", PrimitiveKind.Float64)
    val builtinOps = listOf(
        createBuiltinOp(BuiltinOpKind.CONVERT_I8_to_I16, typeInt16, typeInt8),
        createBuiltinOp(BuiltinOpKind.CONVERT_I16_TO_I32, typeInt32, typeInt16),
        createBuiltinOp(BuiltinOpKind.CONVERT_F32_TO_F64, typeInt64, typeInt32),
        createBuiltinOp(BuiltinOpKind.CONVERT_F32_TO_F64, typeFloat64, typeFloat32),
        createBuiltinOp(BuiltinOpKind.ADD_I8, typeInt8, typeInt8, typeInt8),
        createBuiltinOp(BuiltinOpKind.ADD_I16, typeInt16, typeInt16, typeInt16),
        createBuiltinOp(BuiltinOpKind.ADD_I32, typeInt32, typeInt32, typeInt32),
        createBuiltinOp(BuiltinOpKind.ADD_I64, typeInt64, typeInt64, typeInt64),
        createBuiltinOp(BuiltinOpKind.ADD_F32, typeFloat32, typeFloat32, typeFloat32),
        createBuiltinOp(BuiltinOpKind.ADD_F64, typeFloat64, typeFloat64, typeFloat64),
    )

    private fun createPrimitive(name: String, kind: PrimitiveKind): Type {
        val p = Declaration.Primitive(name, kind, SourceRef.EMPTY)
        systemModulePart.declarations.add(p)
        return Type.Named(name, SourceRef.EMPTY, "System", p)
    }

    private fun createBuiltinOp(
        kind: BuiltinOpKind, result: Type, vararg params: Type
    ): BuiltinOp {
        return BuiltinOp(
            kind.name.lowercase(), Type.Tuple(
                params.toList().mapIndexed { index, type -> Field("value$index", type, SourceRef.EMPTY) },
                SourceRef.EMPTY
            ), result, kind
        )
    }

    fun findOrCreateModule(name: String): Module {
        return modules.firstOrNull { it.name == name } ?: (Module(name).also { modules += it })
    }

    init {
        systemModulePart.declarations += Declaration.Variable("true", ExpressionRef(Expression.LiteralBool(true, SourceRef.EMPTY, typeBool), typeBool), typeBool, SourceRef.EMPTY, global = true)
        systemModulePart.declarations += Declaration.Variable("false", ExpressionRef(Expression.LiteralBool(false, SourceRef.EMPTY, typeBool), typeBool), typeBool, SourceRef.EMPTY, global = true)
    }
}