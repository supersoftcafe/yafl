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
    ast::Module* findOrCreateModule(std::vector<std::string> const & name);
    ParseState<bool> parseModule(Tokens tk);

public:
    ast::Ast ast;

    explicit GrammarParser();
    ~GrammarParser();

    ParseState<bool> parseFile(Tokens);
};


#endif //YAFLCC_GRAMMARPARSER_H
