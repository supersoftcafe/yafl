//
// Created by Michael Brown on 19/03/2022.
//

#ifndef YAFLCC_GRAMMARPARSER_H
#define YAFLCC_GRAMMARPARSER_H

#include "Ast.h"
#include "Token.h"
#include <vector>
#include <memory>

class GrammarParser {
public:
    explicit GrammarParser();
    ~GrammarParser();

    ParseState<std::shared_ptr<ast::Ast>> parse(Tokens);
};


#endif //YAFLCC_GRAMMARPARSER_H
