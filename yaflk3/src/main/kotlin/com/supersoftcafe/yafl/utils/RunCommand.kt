package com.supersoftcafe.yafl.utils

import java.io.IOException

fun String.runCommand(input: String): Either<String,List<String>> {
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

        return if (result != 0) Either.Error(listOf(stderr)) else Either.Some(stdout)

    } catch(e: IOException) {
        e.printStackTrace()
        return Either.Error(listOf(e.stackTraceToString()))
    }
}

