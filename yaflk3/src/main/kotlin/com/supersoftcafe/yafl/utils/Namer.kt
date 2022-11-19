package com.supersoftcafe.yafl.utils

data class Namer(val name: String, val odd: Boolean) {
    constructor(prefix: String) : this(prefix, false)

    operator fun plus(count: Int): Namer {
        val string = count.toString()
        val suffix = if (odd)
            string.map { it + TO_ALPHA }.joinToString("")
        else string
        return copy(name = "$name$suffix", odd = !odd)
    }

    override fun toString() = name

    companion object {
        private const val TO_ALPHA = 'a' - '0'
    }
}
