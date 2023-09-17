package com.supersoftcafe.yafl.utils

import java.io.File
import java.io.IOException
import java.net.URI
import java.net.URL

abstract class TextSource(val location: URI) {

    abstract fun readContent(): Either<String>


    companion object {
        fun fromFile(file: File) = object: TextSource(file.toURI()) {
            override fun readContent() = try {
                some(file.readText())
            } catch (e: IOException) {
                none(ErrorInfo.ParseExceptionInfo(file, e))
            }
        }

        fun fromURL(file: URL) = object: TextSource(file.toURI()) {
            override fun readContent() = try {
                some(file.readText())
            } catch (e: IOException) {
                none(ErrorInfo.ParseExceptionInfo(file, e))
            }
        }

        fun fromString(file: String, content: String) = object: TextSource(URI.create(file)) {
            override fun readContent() = some(content)
        }
    }
}
