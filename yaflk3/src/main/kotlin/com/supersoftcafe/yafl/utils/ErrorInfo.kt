package com.supersoftcafe.yafl.utils

import com.supersoftcafe.yafl.models.ast.SourceRef
import java.io.File

sealed class ErrorInfo {
    data class StringErrorInfo(val message: String) : ErrorInfo() {
        override fun toString() = message
    }

    data class FileOffsetInfo(val file: String, val line: Int, val offset: Int, val message: String?) : ErrorInfo() {
        constructor(file: File, line: Int, offset: Int, message: String?) : this(file.toString(), line, offset, message)
        override fun toString() = "$file: $line $offset $message"
    }

    data class ParseExceptionInfo(val file: String, val exception: Exception) : ErrorInfo() {
        constructor(file: File, exception: Exception) : this(file.toString(), exception)
        override fun toString() = "Failed to parse \"$file\" with exception \"${exception.message}\""
    }

    data class StringWithSourceRef(val sourceRef: SourceRef, val message: String) : ErrorInfo() {
        override fun toString() = "$sourceRef: $message"
    }
}
