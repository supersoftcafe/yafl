//
// Created by mbrown on 09/04/24.
//

#ifndef YAFLC_TOKENIZER_H
#define YAFLC_TOKENIZER_H

#include <vector>
#include <string_view>

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
    };

    struct Token {
        Kind kind;
        size_t line;
        size_t offset;
        size_t line_indent;
        string_view text;
    };

    vector<Token> tokenize(string_view text);
};

#endif //YAFLC_TOKENIZER_H

