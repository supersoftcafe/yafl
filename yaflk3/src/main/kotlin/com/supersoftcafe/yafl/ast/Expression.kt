package com.supersoftcafe.yafl.ast

import com.supersoftcafe.yafl.utils.Namer


sealed class Expression {
    abstract val sourceRef: SourceRef
    abstract val typeRef: TypeRef?

    data class RawPointer(override val sourceRef: SourceRef, override val typeRef: TypeRef.Primitive, val field: Expression) : Expression()

    data class Assert(override val sourceRef: SourceRef, override val typeRef: TypeRef?, val value: Expression, val condition: Expression, val message: String) : Expression()

    data class ArrayLookup(override val sourceRef: SourceRef, override val typeRef: TypeRef?, val array: Expression, val index: Expression) : Expression()

    data class LoadData(override val sourceRef: SourceRef, override val typeRef: TypeRef?, val dataRef: DataRef): Expression()

    data class LoadMember(override val sourceRef: SourceRef, override val typeRef: TypeRef?, val base: Expression, val name: String, val id: Namer? = null): Expression()

    data class NewKlass(override val sourceRef: SourceRef, override val typeRef: TypeRef, val parameter: Expression.Tuple): Expression()

    data class If(override val sourceRef: SourceRef, override val typeRef: TypeRef?, val condition: Expression, val ifTrue: Expression, val ifFalse: Expression): Expression()

    data class Lambda(override val sourceRef: SourceRef, override val typeRef: TypeRef?, val parameters: List<Declaration.Let>, val body: Expression, val id: Namer): Expression()

    data class Tuple(override val sourceRef: SourceRef, override val typeRef: TypeRef?, val fields: List<TupleExpressionField>): Expression()

    data class Call(override val sourceRef: SourceRef, override val typeRef: TypeRef?, val callable: Expression, val parameter: Expression.Tuple): Expression()

    data class Parallel(override val sourceRef: SourceRef, override val typeRef: TypeRef?, val parameter: Expression.Tuple): Expression()

    data class Llvmir(override val sourceRef: SourceRef, override val typeRef: TypeRef, val pattern: String, val inputs: List<Expression>) : Expression()

    data class Integer(override val sourceRef: SourceRef, override val typeRef: TypeRef, val value: Long): Expression()

    data class Float(override val sourceRef: SourceRef, override val typeRef: TypeRef, val value: Double): Expression()

    data class Characters(override val sourceRef: SourceRef, override val typeRef: TypeRef, val value: String): Expression()

    data class Let(override val sourceRef: SourceRef, override val typeRef: TypeRef?, val let: Declaration.Let, val tail: Expression): Expression()

    // data class Function(override val typeRef: TypeRef?, val function: Declaration.Function, val tail: Expression): Expression()
}
