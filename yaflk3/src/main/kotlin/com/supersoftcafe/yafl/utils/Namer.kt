package com.supersoftcafe.yafl.utils

data class Namer(private val name: String) {
    operator fun plus(count: Int): Namer {
        val string = count.toString()
        val suffix = if (name.isEmpty() || name.last().isDigit())
            string.map { it + TO_ALPHA }.joinToString("")
        else string
        return copy(name = "$name$suffix")
    }

    fun toString(count: Int) = plus(count).toString()
    override fun toString() = name

    companion object {
        private const val TO_ALPHA = 'a' - '0'
    }
}
