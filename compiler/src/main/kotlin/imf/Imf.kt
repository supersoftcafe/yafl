package imf

import java.math.BigInteger


data class Imf(
    val functions: List<Function> = emptyList(),    // Includes let statements. They are functions too
    val structures: List<Structure> = emptyList()
)

enum class Flag {
    DUMMY
}

interface Type {
    val cname: String?
}

data class Structure(override val cname: String?) : Type {

}

enum class Primitive(override val cname: String?) : Type {
    INTEGER("int32_t"), LONG("int64_t"), FLOAT("float"), DOUBLE("double")
}

data class Function(
    val name: String,
    val parameters: List<Function>,
    val type: Type? = null,
    val cname: String? = null,
    val operations: List<Operation> = emptyList()
)


sealed class Operation {
    abstract val flags: Set<Flag>
    abstract val cname: String
    abstract val type: Type?

    data class LoadIntegerConstant(
        override val cname: String,
        val value: BigInteger,
        override val type: Type? = null,
        override val flags: Set<Flag> = emptySet()
    ) : Operation()

    data class LoadFloatConstant(
        override val cname: String,
        val value: Double,
        override val type: Type? = null,
        override val flags: Set<Flag> = emptySet()
    ) : Operation()

    // Replace with Invoke of add method. Primitives will have traits with
    // specialised add methods. Custom add methods may use generics.
    data class Add(
        override val cname: String,
        val left: String,
        val right: String,
        override val type: Type? = null,
        override val flags: Set<Flag> = emptySet()
    ) : Operation()

    // Replace with Invoke of conversion method
    // That will later be found in a trait, and compiler provided for primitives
    data class PromoteType(
        override val cname: String,
        val input: String,
        override val type: Type? = null,
        override val flags: Set<Flag> = emptySet()
    ) : Operation()


    // Every operation produces a register output from inputs
    // The final operation is implicitly the return value
    // Inner functions are move to outer scope by implicitly
    //     passing outer scope value access as the first parameters
    // Primitive operations on a structure or class type are
    //     transformed to function calls to the appropriate
    //     implementation, or are an error.
}
