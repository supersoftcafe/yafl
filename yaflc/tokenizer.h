//
// Created by mbrown on 09/04/24.
//

#ifndef YAFLC_TOKENIZER_H
#define YAFLC_TOKENIZER_H

#include <vector>
#include <string_view>
#include "error.h"

namespace tk {
    using namespace std;

    enum Kind {
        UNEXPECTED,
        WHITESPACE,
        MODULE,
        IMPORT,
        LET,
        EQUALS,
        IDENTIFIER,
        COMMENT,
        DOT,
        INTEGER,
        STRING,
    };

    struct Token {
        Kind kind;
        LineRef line;
        size_t indent;
        string_view text;

        Token(Kind kind, LineRef line, size_t indent, string_view text) : kind(kind), line(line), indent(indent), text(text) { }

        // Delete copy constructor and assignment operator
        Token(const Token&) = delete;
        Token& operator=(const Token&) = delete;
        Token(Token&&) = default;
    };

    vector<Token> tokenize(string_view text);
};

#endif //YAFLC_TOKENIZER_H

