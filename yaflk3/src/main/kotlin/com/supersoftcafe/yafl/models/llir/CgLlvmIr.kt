package com.supersoftcafe.yafl.models.llir

data class CgLlvmIr(val stdlib: String = "", val types: String = "", val declarations: String = "") {
    fun withType(type: String) = copy(types = types + type)
    fun withDeclaration(declaration: String) = copy(declarations = declarations + declaration)
    override fun toString() = stdlib + types + declarations
    operator fun plus(o: CgLlvmIr) = CgLlvmIr(stdlib = if (stdlib.isEmpty()) o.stdlib else stdlib, types = types + o.types, declarations = declarations + o.declarations)
}
