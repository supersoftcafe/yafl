package com.supersoftcafe.yaflc.llvm

sealed interface IrType {
    val llvmType: String
    val simpleName: String
}
enum class IrPrimitive(override val llvmType: String, override val simpleName: String) : IrType {
    Bool("i1", "b"), Int8("i8", "1"), Int16("i16", "2"), Int32("i32", "4"), Int64("i64", "8"), Float32("float", "f"), Float64("double", "d"),
    Pointer("i8*", "p"), Lambda("%lambda", "l"), Object("%object*", "o");
    override fun toString() = llvmType
}
class IrTuple(val fields: List<IrType>) : IrType {
    override val llvmType = if (fields.isEmpty()) "void" else fields.joinToString(",", "{", "}")
    override val simpleName = fields.joinToString("", "t", "z") { it.simpleName }
    override fun toString() = llvmType
}
class IrLambda(val result: IrType, val params: IrTuple) : IrType {
    override val llvmType get() = "%lambda"
    val typeIfGlobal = "$result(${(listOf(IrPrimitive.Object) + params.fields).joinToString()} )*"
    val typeIfMember = "$result(${(listOf(IrPrimitive.Object) + params.fields).joinToString()} )*"
    override val simpleName = params.fields.joinToString("F", result.toString())
    override fun toString() = llvmType
}
fun IrVoid() = IrTuple(listOf())
class IrStruct(
    val name: String,
    override val llvmType: String,
    override val simpleName: String,
    val onHeap: Boolean,
    private val getTuple: () -> IrTuple,
) : IrType {
    val tuple get() = getTuple()
    override fun toString() = llvmType
}

//class IrInterface(
//    val vtName: String,
//    override val llvmType: String,
//    override val simpleName: String,
//    val functions: List<IrInterfaceFunction>
//) : IrType {
//    override fun toString() = llvmType
//}

class IrInterfaceFunction(
    val slot: Int,
    val llvmType: String,
    val result: IrType,
    val parameters: List<IrType>
) {
    override fun toString() = llvmType
}


class IrLabel(val name: String)

class IrVariable(val name: String, val type: IrType, var owned: Boolean = false)

sealed class IrResult(val type: IrType)
class IrValue(val value: String, type: IrType) : IrResult(type) {
    override fun toString() = value
}
class IrRegister(val name: String, type: IrType, var owned: Boolean = false) : IrResult(type) {
    override fun toString() = "%$name"
}
class IrFunction(val name: String, val result: IrType) {
    private val _variables = mutableListOf<IrVariable>()
    private val _registers = mutableListOf<IrRegister>()
    private val _labels    = mutableListOf<IrLabel>()

    val variables: List<IrVariable> get() = _variables
    val registers: List<IrRegister> get() = _registers
    val labels   : List<IrLabel   > get() = _labels

    // Function declaration and lots of alloca
    val enter = mutableListOf<String>()

    // The actual code of the function
    val body = mutableListOf<String>()

    // Final cleanup actions
    val exit = mutableListOf<String>()

    // Registers that point to stack memory of the actual value. Parameters and let statements.
    fun nextVariable(type: IrType) = IrVariable("v${_variables.size}", type).also(_variables::add)

    // Temporary results of expressions as llvm register values.
    fun nextRegister(type: IrType, owned: Boolean = false) = IrRegister("r${_registers.size}", type, owned).also(_registers::add)

    // Just labels
    fun nextLabel() = IrLabel("l${_labels.size}").also(_labels::add)


    override fun toString(): String {
        val ls = System.lineSeparator()
        return (enter + body + exit).joinToString(ls, ls, ls)
    }
}

