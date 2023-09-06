package com.supersoftcafe.yafl.passes.p1_parse

import com.supersoftcafe.yafl.models.ast.SourceRef
import org.antlr.v4.runtime.ParserRuleContext
import org.antlr.v4.runtime.tree.TerminalNode


fun ParserRuleContext.toSourceRef(file: String) = SourceRef(file, this)

