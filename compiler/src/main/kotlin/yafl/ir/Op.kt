package yafl.ir

sealed class Type {
    object Bool : Type()
    object Int8 : Type()
    object Int16 : Type()
    object Int32 : Type()
    object Int64 : Type()
    object Float32 : Type()
    object Float64 : Type()
    object Pointer : Type()
    data class Struct(val fields: List<Type>) : Type()
    data class Array(val type: Type, val size: Int) : Type()
}

enum class BinOp { ADD, SUB, MUL, DIV, MOD }
enum class CmpOp { EQ, LT, LE, GT, GE, NE }

data class PhiSource(val src: String, val arg: String)

sealed class Op() {
    open val result: Field? = null
    open val inputs: List<String> = listOf()


    // copy rtarget, rsource
    // sload rtarget, rsource->dfsdf
    // sstore rtarget->dstsjt, rsource
    // aload rtarget, rsource->dfsdf[rsource2]
    // astore rtarget->dfsdf[rtarget2], rsource

    data class LoadC(override val result: Field, val value: Any) : Op()

    data class AddressOfFunction(override val result: Field, val name: String) : Op()

    data class Call(override val result: Field, val funRef: String, val args: List<String>) : Op() {
        override val inputs get() = args + funRef }

    data class BinRC(override val result: Field, val arg1: String, val binOp: BinOp, val arg2: Any) : Op() {
        override val inputs get() = listOf(arg1) }

    data class CmpRC(override val result: Field, val arg1: String, val cmpOp: CmpOp, val arg2: Any) : Op() {
        override val inputs get() = listOf(arg1) }

    data class JumpIf(val condition: String, val targetIfFalse: String, val targetIfTrue: String) : Op() {
        override val inputs get() = listOf(condition) }

    data class Jump(val target: String) : Op()

    data class Phi(override val result: Field, val sources: List<PhiSource>) : Op() {
        override val inputs get() = sources.map { it.arg } }

    data class ReturnR(val arg1: String) : Op() {
        override val inputs get() = listOf(arg1) }
}

data class CodeBlock(
    val name: String,
    val operations: List<Op>)

data class Field(
    val name: String,
    val type: Type)

data class Function(
    val name: String,
    val parameters: List<Field>,
    val result: Type,
    val blocks: List<CodeBlock>)

data class Program(
    val functions: List<Function>)