package com.supersoftcafe.yafl.ast

sealed class Declaration {
    abstract val id: Long
    abstract val name: String
    abstract val isGlobal: Boolean
    abstract val sourceRef: SourceRef

    sealed class Data : Declaration()
    sealed class Type : Declaration()



//    data class Function(override val name: String, override val id: Long, override val isGlobal: Boolean, val parameter: Parameter.Tuple, val body: Expression) : Declaration()

    data class Let(override val sourceRef: SourceRef, override val name: String, override val id: Long, override val isGlobal: Boolean, val typeRef: TypeRef?, val body: Expression?) : Data()

    data class Alias(override val sourceRef: SourceRef, override val name: String, override val id: Long, override val isGlobal: Boolean, val typeRef: TypeRef) : Type()

//    data class Interface(override val name: String, override val id: Long, override val isGlobal: Boolean, val extends: Collection<TypeRef>, val members: Collection<FunctionPrototype>) : Declaration()

//    data class Klass(override val name: String, override val id: Long, override val isGlobal: Boolean, val extends: Collection<TypeRef>, val members: Collection<Declaration.Let>, val parameters: TypeRef.Tuple) : Declaration()

    data class Struct(override val sourceRef: SourceRef, override val name: String, override val id: Long, override val isGlobal: Boolean, val parameters: List<Declaration.Let>) : Type()

//    data class Enum(override val name: String, override val id: Long, override val isGlobal: Boolean) : Declaration()
}

