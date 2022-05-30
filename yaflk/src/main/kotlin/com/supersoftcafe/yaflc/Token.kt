package com.supersoftcafe.yaflc

import kotlinx.collections.immutable.PersistentList


data class Token(val kind: TokenKind, val text: String, val indent: Int)

