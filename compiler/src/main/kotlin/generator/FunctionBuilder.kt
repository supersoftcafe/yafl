package generator



class FunctionBuilder(val cname: String, val ctype: String) {
    private val typeInfo = Register(cname, ctype)
    private val registers = mutableListOf<Register>()
    private val operations = mutableListOf<Operation>()

    fun addRegister(ctype: String, isParameter: Boolean = false): Register {
        return Register("reg_${registers.size}", ctype, isParameter)
    }

    fun addOperation(operation: Operation) {
        operations += operation
    }

    fun build(): String {
        val sb = StringBuilder()

        fun append(sb: StringBuilder, r: Register) = sb.append(ctype).append(' ').append(cname)

        append(sb, typeInfo).append('(')
        for (reg in registers) {
            if (reg.isParameter) {
                if (sb.last() != '(')
                    sb.append(", ")
                append(sb, reg)
            }
        }
        sb.append(")\n{\n")

        for (reg in registers) {
            if (!reg.isParameter) {
                sb.append("    ")
                append(sb, reg)
                sb.append(';')
            }
        }
        sb.append("\n")

        for (op in operations) {
            op.Emit(sb)
        }

        sb.append("}\n\n")
        return sb.toString()
    }
}