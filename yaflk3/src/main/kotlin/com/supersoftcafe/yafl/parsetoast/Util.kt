package com.supersoftcafe.yafl.parsetoast

import com.supersoftcafe.yafl.ast.SourceRef
import org.antlr.v4.runtime.ParserRuleContext


fun ParserRuleContext.toSourceRef(file: String) = SourceRef(file, this)
