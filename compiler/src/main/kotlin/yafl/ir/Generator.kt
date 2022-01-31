package yafl.ir


private fun Type.toSimpleName(): String = when (this) {
    is Type.Bool -> "B"
    is Type.Int8 -> "b"
    is Type.Int16 -> "s"
    is Type.Int32 -> "i"
    is Type.Int64 -> "l"
    is Type.Float32 -> "f"
    is Type.Float64 -> "d"
    is Type.Pointer -> "p"
    is Type.Struct -> "S${fields.joinToString(""){it.toSimpleName()}}z"
    is Type.Array -> "A${size}z${type.toSimpleName()}"
}

private fun Type.toUniqueName(): String = when (this) {
    is Type.Bool -> "bool"
    is Type.Int8 -> "int8_t"
    is Type.Int16 -> "int16_t"
    is Type.Int32 -> "int32_t"
    is Type.Int64 -> "int64_t"
    is Type.Float32 -> "float"
    is Type.Float64 -> "double"
    is Type.Pointer -> "pointer"
    is Type.Struct -> toSimpleName()
    is Type.Array -> throw IllegalArgumentException("Array can't have a unique name")
}

private fun Type.toForward(): String {
    val name = toUniqueName()
    return when (this) {
        is Type.Bool, is Type.Int8, is Type.Int16,
        is Type.Int32, is Type.Int64, is Type.Float32,
        is Type.Float64, Type.Pointer -> "/* Forward $name */\n"
        is Type.Array -> "/* Forward ${type.toUniqueName()}[$size] */\n"

        is Type.Struct -> "typedef struct _$name $name;\n"
    }
}

private fun Type.toNamedVariable(name: String): String {
    return if (this is Type.Array) {
        "${type.toUniqueName()} $name[$size]"
    } else {
        "${toUniqueName()} $name"
    }
}

private fun Type.toDeclaration(): String {
    val name = toUniqueName()
    return when (this) {
        is Type.Bool, is Type.Int8, is Type.Int16,
        is Type.Int32, is Type.Int64, is Type.Float32,
        is Type.Float64 -> "/* Declare $name */\n"
        is Type.Array -> "/* Declare ${type.toUniqueName()}[$size] */\n"

        is Type.Pointer -> "typedef void* pointer;\n"
        is Type.Struct -> "typedef struct _$name { ${fields.withIndex().joinToString("") { "${it.value.toNamedVariable("f${it.index}")};" }} } $name;\n"
    }
}

private fun Function.toForward(): String {
    return "${result.toUniqueName()} $name(${parameters.joinToString(", ") { it.type.toUniqueName() }});\n"
}

private fun CmpOp.toC(): String {
    return when (this) {
        CmpOp.EQ -> "!="; CmpOp.NE -> "!="
        CmpOp.LE -> "<="; CmpOp.LT -> "<"
        CmpOp.GE -> ">="; CmpOp.GT -> ">"
    }
}

private fun BinOp.toC(): String {
    return when (this) {
        BinOp.ADD -> "+"
        BinOp.SUB -> "-"
        BinOp.MUL -> "*"
        BinOp.DIV -> "/"
        BinOp.MOD -> "%"
    }
}

private fun Op.toC(phiTargets: List<Pair<String, List<String>>>): String {
    fun toTarget(name: String): String {
        val phiNames = phiTargets.filter { name in it.second }.joinToString("") { "${it.first} = " }
        return "$phiNames$name"
    }
    return when (this) {
        is Op.LoadC -> "    ${toTarget(result.name)} = $value;\n"
        is Op.BinRC -> "    ${toTarget(result.name)} = $arg1 ${binOp.toC()} $arg2;\n"
        is Op.CmpRC -> "    ${toTarget(result.name)} = $arg1 ${cmpOp.toC()} $arg2;\n"
        is Op.JumpIf -> "    if ($condition) goto $targetIfTrue; else goto $targetIfFalse;\n"
        is Op.Jump -> "    goto $target;\n"
        is Op.Phi -> "    // Phi\n"
        is Op.ReturnR -> "    return $arg1;\n"
    }
}

private fun CodeBlock.toC(phiTargets: List<Pair<String, List<String>>>): String {
    return "$name:;\n${operations.joinToString("") { it.toC(phiTargets) }}"
}

private fun Function.toDeclaration(): String {
    val methodSig = "${result.toUniqueName()} $name(${parameters.joinToString(", ") { "${it.type.toUniqueName()} ${it.name}" }})"
    val forwardDecls = blocks.flatMap { it.operations.mapNotNull { it.result } }.joinToString("") { "    ${it.type.toUniqueName()} ${it.name};\n" }
    val phiTargets = blocks.flatMap { it.operations.filterIsInstance<Op.Phi>().map { it.result.name to it.sources.map { it.arg }}}
    val bodyOfCode = blocks.joinToString("") { it.toC(phiTargets) }
    return "$methodSig {\n$forwardDecls$bodyOfCode}\n"
}

private tailrec fun List<Type.Struct>.topologicalSort(result: List<Type.Struct>): List<Type.Struct> {
    return if (isEmpty()) {
        result
    } else {
        val decisions = map { parent -> none { child -> parent in child.fields } }
        val childless = filterIndexed { index, _ -> decisions[index] }
        val remainder = filterIndexed { index, _ -> !decisions[index] }
        remainder.topologicalSort(result + childless)
    }
}

fun irToC(ir: Program): String {
    val allTypes = ir.functions.flatMap { it.parameters.map { it.type } + it.result + it.blocks.flatMap { it.operations.mapNotNull { it.result?.type } } }.distinct()
    val sortedTypes = allTypes.filter { it !is Type.Struct} + allTypes.filterIsInstance<Type.Struct>().topologicalSort(listOf()).reversed()

    val headers = "#include <stdbool.h>\n#include <stdint.h>\n"
    val typeForwards = "\n\n// Forward declare types\n\n${sortedTypes.joinToString("") { it.toForward() }}"
    val typeDeclares = "\n\n// Actual declare types\n\n${sortedTypes.joinToString("") { it.toDeclaration() }}"
    val methodForwards = "\n\n// Forward declare methods\n\n${ir.functions.joinToString("") { it.toForward()  }}"
    val methodDeclares = "\n\n// Forward declare methods\n\n${ir.functions.joinToString("") { it.toDeclaration()  }}"

    return headers + typeForwards + typeDeclares + methodForwards + methodDeclares
}

