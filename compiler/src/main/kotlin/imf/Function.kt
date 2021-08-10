package imf

data class Function(
    val name: String,
    val parameters: List<Function>,
    val type: Type? = null,
    override val cname: String? = null,

    val locals: List<Function> = emptyList(),
    val expression: Operation? = null
) : Type