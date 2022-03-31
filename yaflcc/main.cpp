
#include "Token.h"
#include "TokenParser.h"
#include "GrammarParser.h"
#include "TypeResolver.h"
#include <iostream>
#include <fstream>
#include <vector>
#include <regex>

using namespace std;

int main(int argc, char** argv) {
    std::ifstream        in { argv[1] };
    TokenParser tokenParser { string(istreambuf_iterator<char>(in), istreambuf_iterator<char>()) };
    ast::Ast ast;

    GrammarParser grammarParser(ast, tokenParser.tokens);
    if (!std::empty(grammarParser.errors)) {
        cerr << "Failed" << endl;
        for (auto& error : grammarParser.errors)
            cerr << "  " << error << endl;
        return 1;
    }

    TypeResolver typeResolver(ast);
    if (!std::empty(typeResolver.errors)) {
        cerr << "Failed" << endl;
        for (auto& error : typeResolver.errors)
            cerr << "  " << error << endl;
        return 2;
    }

    return 0;
}
