package com.supersoftcafe.yafl.lexer

import com.supersoftcafe.yafl.utils.SourceRef

data class Token(val kind: TokenKind, val text: String, val sourceRef: SourceRef)

