package com.supersoftcafe.yaflc.llvm

sealed interface IrType {
    val llvmType: String
    val simpleName: String
}
enum class IrPrimitive(override val llvmType: String, override val simpleName: String) : IrType {
    Bool("i1", "b"), Int8("i8", "1"), Int16("i16", "2"), Int32("i32", "4"), Int64("i64", "8"), Float32("float", "f"), Float64("double", "d");
    override fun toString() = llvmType
}
class IrTuple(val fields: List<IrType>) : IrType {
    override val llvmType get() = fields.joinToString(",", "{", "}")
    override val simpleName get() = fields.joinToString("", "t", "z") { it.simpleName }
    override fun toString() = llvmType
}
class IrStruct(val name: String, val type: () -> IrTuple) : IrType {
    override val llvmType get() = "%struct_$name"
    override val simpleName get() = "_str_${name}_"
    override fun toString() = llvmType
}


class IrLabel(val name: String)
class IrVariable(val name: String, val type: IrType)
class IrFunction(val name: String, val result: IrType) {
    private val _parameters = mutableListOf<IrVariable>()
    private val _variables  = mutableListOf<IrVariable>()
    private val _labels = mutableListOf<IrLabel>()
    private var uniqueValue = 0

    val parameters: List<IrVariable> get() = _parameters
    val variables: List<IrVariable> get() = _variables
    val labels: List<IrLabel> get() = _labels

    val preamble = mutableListOf<String>()
    val body = mutableListOf<String>()

    fun nextParameter(type: IrType) = IrVariable("p_${++uniqueValue}", type).also(_parameters::add)
    fun nextVariable(type: IrType) = IrVariable("v_${++uniqueValue}", type).also(_variables::add)
    fun nextLabel() = IrLabel("l_${++uniqueValue}").also(_labels::add)


    override fun toString(): String {
        val ls = System.lineSeparator()
        return (preamble + body).joinToString(ls, ls, ls)
    }
}
