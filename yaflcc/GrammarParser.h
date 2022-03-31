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
private:
    ParseState<bool> parseModule(Tokens tk);
    ast::Ast& ast;

public:
    std::vector<std::string> errors;

    GrammarParser(ast::Ast& ast, Tokens tokens);
    ~GrammarParser();
};


#endif //YAFLCC_GRAMMARPARSER_H
