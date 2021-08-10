package imf


data class Imf(
    val functions: List<Function> = emptyList(),    // Includes let statements. They are functions too
    val structures: List<Structure> = emptyList()
)


