package com.supersoftcafe.yaflc.codegen

fun String.escape() =
    when (firstOrNull()) {
        '%', '@' -> "\"$this\""
        else -> this
    }