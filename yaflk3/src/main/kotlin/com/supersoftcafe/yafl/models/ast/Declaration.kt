package com.supersoftcafe.yafl.models.ast

import com.supersoftcafe.yafl.passes.p4_optimise.toSignature
import com.supersoftcafe.yafl.utils.Namer

sealed class Declaration {
    abstract val id: Namer
    abstract val name: String
    abstract val scope: Scope
    abstract val sourceRef: SourceRef
    abstract val guidance: List<Guidance>

    sealed class Data : Declaration() {
        abstract val signature: String?
        abstract val typeRef: TypeRef?
        abstract val sourceTypeRef: TypeRef?
        abstract val body: Expression?
    }

    sealed class Type : Declaration() {
    }

    data class Alias(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        val typeRef: TypeRef,
        override val guidance: List<Guidance> = listOf(),
    ) : Type() {
        override fun toString() = "alias $name"
    }

    data class Enum(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        val members: List<EnumEntry>,
        override val guidance: List<Guidance> = listOf(),
    ) : Type() {
        override fun toString() = "enum $name"
    }

    data class Klass(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        val parameters: List<Let>,
        val members: List<Function>,
        val extends: List<TypeRef>,
        val isInterface: Boolean,
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
        val dynamicArraySize: Expression? = null,
        val arraySize: Long? = null,
        override val signature: String? = null,
        override val guidance: List<Guidance> = listOf(),

        val destructure: List<Let> = listOf(),
    ) : Data() {
        override fun toString() = "let $name"

        fun isEmpty() = name == "_" && typeRef == null && destructure.isEmpty()
        fun flatten(): List<Let> = if (destructure.isEmpty()) listOf(this) else destructure.flatMap { it.flatten() }
        fun map(op: (Let) -> Let): Let = if (destructure.isEmpty()) op(this) else copy(destructure = destructure.map(op))
        fun unwrapSingleton(): Let = destructure.singleOrNull()?.unwrapSingleton() ?: this
        fun findByName(name: String): List<Declaration.Let> = destructure.flatMap { it.findByName(name) } + listOfNotNull(takeIf { it.name == name })

        companion object {
            fun newThis(
                sourceRef: SourceRef,
                id: Namer,
                typeRef: TypeRef?,
            ) = Let(
                sourceRef = sourceRef,
                name = "this",
                id = id,
                scope = Scope.Local,
                typeRef = typeRef,
                sourceTypeRef = typeRef,
                body = null,
            )

            fun unpack(
                sourceRef: SourceRef,
                values: Iterable<Declaration.Let>
            ) = Declaration.Let(
                sourceRef = sourceRef,
                name = "",
                id = Namer.DEFAULT,
                scope = Scope.Local,
                typeRef = null,
                sourceTypeRef = null,
                body = null,
            )

            val EMPTY = Declaration.Let(
                SourceRef.EMPTY, "_", Namer.DEFAULT, Scope.Local, null, null, null)
        }
    }

    data class Function(
        override val sourceRef: SourceRef,
        override val name: String,
        override val id: Namer,
        override val scope: Scope,
        val thisDeclaration: Let,
        val parameter: Let,
        val returnType: TypeRef?,
        val sourceReturnType: TypeRef?,
        override val body: Expression?,
        val attributes: Set<String> = setOf(),
        override val guidance: List<Guidance> = listOf(),
        val extensionType: TypeRef? = null,
    ) : Data() {
        override fun toString() = "fun $name"
        override val typeRef = TypeRef.Callable(parameter.typeRef, returnType ?: body?.typeRef)
        override val sourceTypeRef = TypeRef.Callable(parameter.sourceTypeRef, sourceReturnType)
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

