package com.supersoftcafe.yafl.ast

import com.supersoftcafe.yafl.translate.toSignature
import com.supersoftcafe.yafl.utils.Namer

sealed class Declaration {
    abstract val id: Namer
    abstract val name: String
    abstract val scope: Scope
    abstract val sourceRef: SourceRef

    sealed class Data : Declaration() {
        abstract val signature: String?
        abstract val typeRef: TypeRef?
        abstract val sourceTypeRef: TypeRef?
        abstract val body: Expression?
    }
    sealed class Type : Declaration()


//    data class Struct(
//        override val sourceRef: SourceRef,
//        override val name: String,
//        override val id: Namer,
//        override val isGlobal: Boolean,
//        val parameters: List<Declaration.Let>,
//        val members: List<Declaration.Function>,
//    ) : Type()

    data class Alias(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        val typeRef: TypeRef,
    ) : Type() {
        override fun toString() = "alias $name"
    }

//    data class Interface(
//        override val sourceRef: SourceRef,
//        override val name: String,
//        override val id: Namer,
//        override val scope: Scope,
//        val members: List<FunctionPrototype>,
//        val extends: List<TypeRef>,
//    ) : Declaration()

    data class Klass(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        val parameters: List<Declaration.Let>,
        val members: List<Declaration.Function>,
        val extends: List<TypeRef>,
        val isInterface: Boolean
    ) : Type() {
        override fun toString() = "class $name"
    }

    data class Let(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        override val typeRef: TypeRef?,
        override val sourceTypeRef: TypeRef?,
        override val body: Expression?,
        val arraySize: Long? = null,
        override val signature: String? = null,
    ) : Data() {
        override fun toString() = "let $name"
    }

    data class Function(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        val thisDeclaration: Declaration.Let,
        val parameters: List<Declaration.Let>,
        val returnType: TypeRef?,
        val sourceReturnType: TypeRef?,
        override val body: Expression?,
        val attributes: Set<String> = setOf(),
    ) : Data() {
        override fun toString() = "fun $name"
        override val typeRef = TypeRef.Callable(TypeRef.Tuple(parameters.map { TupleTypeField(it.typeRef, it.name) }), returnType ?: body?.typeRef)
        override val sourceTypeRef = TypeRef.Callable(TypeRef.Tuple(parameters.map { TupleTypeField(it.sourceTypeRef, it.name) }), sourceReturnType)
        override val signature = typeRef.toSignature(name)
    }


//    data class Enum(override val name: String, override val id: Namer, override val isGlobal: Boolean) : Declaration()
}

