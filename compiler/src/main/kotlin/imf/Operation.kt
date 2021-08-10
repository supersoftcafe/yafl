package imf

sealed class Operation {
    abstract val type: Type?

    data class LoadLocalValue(
        val name: String,
        override val type: Type? = null
    ) : Operation()

    data class ConstInt32(
        val value: Int
    ) : Operation() {
        override val type: Primitive = Primitive.INT32
    }

    data class ConstInt64(
        val value: Long
    ) : Operation() {
        override val type: Primitive = Primitive.INT64
    }

    data class ConstFloat32(
        val value: Float
    ) : Operation() {
        override val type: Primitive = Primitive.FLOAT32
    }

    data class ConstFloat64(
        val value: Double
    ) : Operation() {
        override val type: Primitive = Primitive.FLOAT64
    }

    data class Binary(
        val op: BinaryOpType,
        val left: Operation,
        val right: Operation,
        override val type: Type? = null
    ) : Operation()

    data class CastPrimitive(
        val input: Operation,
        override val type: Primitive
    ) : Operation()


    // Inner functions are move to outer scope by implicitly
    //     passing outer scope value access as the first parameters
}