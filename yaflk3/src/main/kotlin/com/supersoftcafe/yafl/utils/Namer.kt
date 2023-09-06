package com.supersoftcafe.yafl.utils

data class Namer(private val name: String) {
    fun fork() = tupleOf(this + 0, this + 1, this + 2, this + 3, this + 4, this + 5)

    operator fun plus(count: Int): Namer {
        val string = count.toString()
        val suffix = if (name.isEmpty() || name.last().isDigit())
            string.map { it + TO_ALPHA }.joinToString("")
        else string
        return copy(name = "$name$suffix")
    }

    operator fun div(tail: Namer): Namer {
        return Namer(name + '/' + tail.name)
    }

    fun toString(count: Int) = plus(count).toString()
    override fun toString() = name

    companion object {
        private const val TO_ALPHA = 'a' - '0'
        val DEFAULT = Namer("a")
    }
}
