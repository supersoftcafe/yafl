package imf

object Transformers {
    fun transform(op: Operation?, typeHint: Type?): Operation? {
        return op
            ?.detectTypes(typeHint)
            ?.upgradeConstPrimitiveTypes(typeHint)
    }

    private fun Operation.walkTree(typeHint: Type?, mutate: Operation.(Type?)->Operation): Operation {
        return mutate(typeHint).run {
            when (this) {
                is Operation.Binary -> {
                    val l = left. walkTree(type, mutate)
                    val r = right.walkTree(type, mutate)
                    copy(left = l, right = r)
                }
                is Operation.CastPrimitive -> {
                    val i = input.walkTree(type, mutate)
                    copy(input = i)
                }
                is Operation.LoadNamedValue -> this
                is Operation.ConstFloat32 -> this
                is Operation.ConstFloat64 -> this
                is Operation.ConstInt32 -> this
                is Operation.ConstInt64 -> this
            }
        }
    }

    private fun Operation.detectTypes(typeHint: Type?): Operation {
        return walkTree(typeHint) {
            when (this) {
                is Operation.Binary -> when {
                    type != null -> this
                    left.type == Primitive.FLOAT64 || right.type == Primitive.FLOAT64 -> copy(type = Primitive.FLOAT64)
                    left.type == Primitive.FLOAT32 || right.type == Primitive.FLOAT32 -> copy(type = Primitive.FLOAT32)
                    left.type == Primitive.INT64 || right.type == Primitive.INT64 -> copy(type = Primitive.INT64)
                    left.type == Primitive.INT32 || right.type == Primitive.INT32 -> copy(type = Primitive.INT32)
                    else -> this
                }
                else -> this
            }
        }
    }

    private fun Operation.upgradeConstPrimitiveTypes(typeHint: Type?): Operation {
        return walkTree(typeHint) {
            when (this) {
                is Operation.ConstInt32 -> when (typeHint) {
                    Primitive.INT64 -> Operation.ConstInt64(value.toLong())
                    Primitive.FLOAT32 -> Operation.ConstFloat32(value.toFloat())
                    Primitive.FLOAT64 -> Operation.ConstFloat64(value.toDouble())
                    else -> this
                }
                is Operation.ConstInt64 -> when (typeHint) {
                    Primitive.FLOAT32 -> Operation.ConstFloat32(value.toFloat())
                    Primitive.FLOAT64 -> Operation.ConstFloat64(value.toDouble())
                    else -> this
                }
                is Operation.ConstFloat32 -> when (typeHint) {
                    Primitive.FLOAT64 -> Operation.ConstFloat64(value.toDouble())
                    else -> this
                }
                else -> this
            }
        }
    }


}
