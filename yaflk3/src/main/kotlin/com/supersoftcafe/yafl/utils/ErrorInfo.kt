package com.supersoftcafe.yafl.utils

import com.supersoftcafe.yafl.models.ast.SourceRef
import java.io.File
import java.net.URI
import java.net.URL

sealed class ErrorInfo {
    data class StringErrorInfo(val message: String) : ErrorInfo() {
        override fun toString() = message
    }

    data class FileOffsetInfo(val file: String, val line: Int, val offset: Int, val message: String?) : ErrorInfo() {
        constructor(file: File, line: Int, offset: Int, message: String?) : this(file.toString(), line, offset, message)
        constructor(file: URI, line: Int, offset: Int, message: String?) : this(file.toString(), line, offset, message)
        constructor(file: URL, line: Int, offset: Int, message: String?) : this(file.toString(), line, offset, message)
        constructor(file: TextSource, line: Int, offset: Int, message: String?) : this(file.location, line, offset, message)
        override fun toString() = "$file: $line $offset $message"
    }

    data class ParseExceptionInfo(val file: String, val exception: Exception) : ErrorInfo() {
        constructor(file: File, exception: Exception) : this(file.toString(), exception)
        constructor(file: URI, exception: Exception) : this(file.toString(), exception)
        constructor(file: URL, exception: Exception) : this(file.toString(), exception)
        constructor(file: TextSource, exception: Exception) : this(file.location, exception)
        override fun toString() = "Failed to parse \"$file\" with exception \"${exception.message}\""
    }

    data class StringWithSourceRef(val sourceRef: SourceRef, val message: String) : ErrorInfo() {
        override fun toString() = "$sourceRef: $message"
    }
}
