package com.supersoftcafe.yaflc.llvm

sealed interface IrType {
    val irName: String
}
enum class IrPrimitive(override val irName: String) : IrType {
    Bool("i1"), Int8("i8"), Int16("i16"), Int32("i32"), Int64("i64"), Float32("float"), Float64("double");

    override fun toString(): String {
        return irName
    }
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
