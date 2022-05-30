package com.supersoftcafe.yaflc

enum class TokenKind(val rx: Regex?) : (Tokens) -> Result<Token> {
    IGNORE("([ \r\n]+)|(#[^\r\n]*\n)"),
    UNKNOWN(null),
    EOI(null),

    BUILTIN("__builtin__"),
    MODULE("module"),
    WHERE("where"),
    FUN("fun"),
    LET("let"),
    USE("use"),
    NAME("(`[^`]+`)|([a-zA-Z_][a-zA-Z_0-9]*)"),
    INTEGER("((0b[_0-1]+)|(0o[_0-7]+)|(0x[_0-9a-f]+)|([+-]?[0-9]+))(i[1248])?"),
    FLOAT("[+-]?([0-9]*)\\.[0-9]+(f[48])?"),
    STRING("\"([^\"]|\\\\\")*\""),
    COLON(":"), QUESTION("\\?"),

    DOT("\\."), AT("@"),
    ADD("\\+"), SUB("-"), MUL("\\*"), DIV("/"), REM("%"),
    SHL("<<"), ASHR(">>"), LSHR(">>>"),
    AND("&"), OR("\\|"), XOR("\\^"), NOT("!"),
    EQ("="), NEQ("!="), LT("<"), LTE("<="), GT(">"), GTE(">="),

    OBRACKET("\\("), CBRACKET("\\)"), OSQUARE("\\["), CSQUARE("\\]"), OCURLEY("\\{"), CCURLEY("\\}"), COMMA(",");

    override fun invoke(tokens: Tokens): Result<Token> = tokens.TokenIs(this)

    constructor(pattern: String) : this(Regex("^($pattern)", RegexOption.MULTILINE))
}