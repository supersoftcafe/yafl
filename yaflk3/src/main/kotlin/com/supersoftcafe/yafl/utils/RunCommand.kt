package com.supersoftcafe.yafl.utils

import java.io.IOException

fun String.runCommand(input: String): Either<String> {
    try {
        val parts = this.split("\\s".toRegex())
        val proc = ProcessBuilder(*parts.toTypedArray())
            .redirectInput(ProcessBuilder.Redirect.PIPE)
            .redirectOutput(ProcessBuilder.Redirect.PIPE)
            .redirectError(ProcessBuilder.Redirect.PIPE)
            .start()

        proc.outputStream.write(input.toByteArray())
        proc.outputStream.close()

        val result = proc.waitFor()
        val stdout = proc.inputStream.bufferedReader().readText()
        val stderr = proc.errorStream.bufferedReader().readText()

        return if (result != 0) error(listOf(stderr)) else some(stdout)

    } catch(e: IOException) {
        e.printStackTrace()
        return error(listOf(e.stackTraceToString()))
    }
}

