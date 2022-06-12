package com.supersoftcafe.yaflc

import kotlinx.collections.immutable.PersistentList
import kotlinx.collections.immutable.persistentListOf
import java.io.IOException
import java.util.concurrent.TimeUnit

typealias Errors = PersistentList<Pair<SourceRef, String>>
typealias Finder = ((Declaration) -> Boolean) -> List<Declaration>
typealias NodePath = PersistentList<INode>

inline fun <T> Iterable<T>.foldErrors(lambda: (T) -> Errors): Errors {
    return fold(persistentListOf()) { list, value -> list.addAll(lambda(value)) }
}

fun String.runCommand(input: String): String? {
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
        val text = proc.inputStream.bufferedReader().readText()

        return if (result == 0) text else null
    } catch(e: IOException) {
        e.printStackTrace()
        return null
    }
}