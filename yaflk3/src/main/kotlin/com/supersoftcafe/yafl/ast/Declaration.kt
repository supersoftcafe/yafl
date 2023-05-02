package com.supersoftcafe.yafl.ast

import com.supersoftcafe.yafl.translate.toSignature
import com.supersoftcafe.yafl.utils.Namer

sealed class Declaration {
    abstract val id: Namer
    abstract val name: String
    abstract val scope: Scope
    abstract val sourceRef: SourceRef
    abstract val guidance: List<Guidance>
    abstract val genericDeclaration: List<Declaration.Generic>

    sealed class Data : Declaration() {
        abstract val signature: String?
        abstract val typeRef: TypeRef?
        abstract val sourceTypeRef: TypeRef?
        abstract val body: Expression?
    }
    sealed class Type : Declaration() {
    }
//    sealed class Other : Declaration()


//    data class Struct(
//        override val sourceRef: SourceRef,
//        override val name: String,
//        override val id: Namer,
//        override val isGlobal: Boolean,
//        val parameters: List<Declaration.Let>,
//        val members: List<Declaration.Function>,
//    ) : Type()

    data class Generic(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        override val guidance: List<Guidance> = listOf(),
    ) : Type() {
        override val genericDeclaration = listOf<Declaration.Generic>()
        override fun toString() = "generic $name"
    }

    data class Alias(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        val typeRef: TypeRef,
        override val genericDeclaration: List<Declaration.Generic>,
        override val guidance: List<Guidance> = listOf(),
    ) : Type() {
        override fun toString() = "alias $name"
    }

    data class Klass(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        val parameters: List<Declaration.Let>,
        val members: List<Declaration.Function>,
        val extends: List<TypeRef>,
        val isInterface: Boolean,
        override val genericDeclaration: List<Declaration.Generic>,
        override val guidance: List<Guidance> = listOf(),
    ) : Type() {
        override fun toString() = if (isInterface) "interface $name" else "class $name"
    }

    data class Let(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        override val typeRef: TypeRef?,
        override val sourceTypeRef: TypeRef?,
        override val body: Expression?,
        override val genericDeclaration: List<Declaration.Generic>,
        val dynamicArraySize: Expression? = null,
        val arraySize: Long? = null,
        override val signature: String? = null,
        override val guidance: List<Guidance> = listOf(),
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
        override val genericDeclaration: List<Declaration.Generic>,
        val attributes: Set<String> = setOf(),
        override val guidance: List<Guidance> = listOf(),
        val extensionType: TypeRef? = null,
    ) : Data() {
        override fun toString() = "fun $name"
        override val typeRef = TypeRef.Callable(TypeRef.Tuple(parameters.map { TupleTypeField(it.typeRef, it.name) }), returnType ?: body?.typeRef)
        override val sourceTypeRef = TypeRef.Callable(TypeRef.Tuple(parameters.map { TupleTypeField(it.sourceTypeRef, it.name) }), sourceReturnType)
        override val signature = typeRef.toSignature(name)
    }
//
//    data class Trait(
//        override val sourceRef: SourceRef,
//        override val name: String,
//        override val id: Namer,
//        override val scope: Scope,
//        val members: List<Declaration.Data>,
//        val extends: List<TypeRef>,
//        override val guidance: List<Guidance> = listOf()
//    ) : Other() {
//        override fun toString() = "trait $name"
//    }
//
//    data class Impl(
//        override val sourceRef: SourceRef,
//        override val name: String,
//        override val id: Namer,
//        override val scope: Scope,
//        val members: List<Declaration.Data>,
//        override val guidance: List<Guidance> = listOf()
//    ) : Other() {
//        override fun toString() = "impl $name"
//    }


//    data class Enum(override val name: String, override val id: Namer, override val isGlobal: Boolean) : Declaration()
}

