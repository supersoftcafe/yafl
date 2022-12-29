package com.supersoftcafe.yafl.tokenizer

enum class TokenKind(val rx: Regex?, val blockStart: Boolean = false) {
    IGNORE("([ \r\n]+)|(#[^\r\n]*\n)"),

    BUILTIN("__builtin__"),
    MODULE("module"),
    STRUCT("struct"),
    INTERFACE("interface", true),
    CLASS("class"),
    WHERE("where"),
    FUN("fun"),
    VAL("val"),
    USE("use"),
    NAME("(`[^`]+`)|([a-zA-Z_][a-zA-Z_0-9]*)"),
    INTEGER("((0b[_0-1]+)|(0o[_0-7]+)|(0x[_0-9a-f]+)|([0-9]+))(i[0-9]+)?"),
    FLOAT("([0-9]*)\\.[0-9]+(f[48])?"),
    STRING("\"([^\"]|\\\\\")*\""),
    COLON(":"), QUESTION("\\?"),

    APPLY("\\|>"),
    DOT("\\."), AT("@"),
    ADD("\\+"), SUB("\\-"), MUL("\\*"), DIV("/"), REM("%"),
    SHL("<<"), ASHR(">>"), LSHR(">>>"),
    AND("&"), OR("\\|"), XOR("\\^"), NOT("!"),
    EQ("="), NEQ("!="), LT("<"), LTE("<="), GT(">"), GTE(">="),

    OBRACKET("\\("), CBRACKET("\\)"), OSQUARE("\\["), CSQUARE("\\]"), OCURLEY("\\{"), CCURLEY("\\}"), COMMA(","),

    EOI(null),
    EOB(null),
    UNKNOWN(".");

    constructor(pattern: String, blockStart: Boolean = false) : this(Regex("^($pattern)", RegexOption.MULTILINE), blockStart)
}