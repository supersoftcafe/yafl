package util

fun <T> T?.toList(next: (T) -> T?): List<T> {
    return if (this == null) {
        emptyList()
    } else {
        listOf(this) + next(this).toList(next)
    }
}