package imf

enum class Primitive(override val cname: String?) : Type {
    INT32("int32_t"), INT64("int64_t"), FLOAT32("float"), FLOAT64("double")
}