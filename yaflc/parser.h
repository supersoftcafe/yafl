//
// Created by mbrown on 09/04/24.
//

#ifndef YAFLC_PARSER_H
#define YAFLC_PARSER_H

#include "tokenizer.h"
#include "error.h"

namespace ps {

    using namespace std;

    enum Kind {
        IDENTIFIER,
        IMPORT,
        MODULE,
    };


    struct Node {
        Kind kind;
        size_t line;
        size_t offset;
        string_view text;
        vector<Node> nodes;
    };

    tuple<vector<Node>, vector<Error>> parse(const vector<tk::Token>& tokens);
};

#endif //YAFLC_PARSER_H
