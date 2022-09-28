package com.supersoftcafe.yaflc.codegen

fun String.llEscape() =
    when (firstOrNull()) {
        '%', '@' -> "\"$this\""
        else -> this
    }