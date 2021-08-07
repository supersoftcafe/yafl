package generator

sealed class Operation {
    open fun Emit(sb: StringBuilder) {
        TODO("Not implemented")
    }

    data class Invoke(val cname: String, val parameters: List<Register>) : Operation()

    data class LoadInt(val register: Register, val value: Int) : Operation() {
        override fun Emit(sb: StringBuilder) {
            sb.append("    ").append(register.cname).append(" = ").append(value).append(";\n")
        }
    }

    data class Return(val register: Register) : Operation() {
        override fun Emit(sb: StringBuilder) {
            sb.append("    return ").append(register.cname).append(";\n")
        }
    }
}
