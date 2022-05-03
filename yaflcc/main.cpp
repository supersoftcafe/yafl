
#include "Token.h"
#include "TokenParser.h"
#include "GrammarParser.h"
#include "TypeResolver.h"
#include "CodeGenerator.h"
#include "Printer.h"
#include "Tools.h"

#include <iostream>
#include <fstream>
#include <vector>
#include <regex>

using namespace ast;
using namespace std;


char const * inputFiles[] = {
        "../samples/system.yafl",
        "../samples/02_hello_world2.yafl",
//        "../samples/add.yafl",
};


int main(int argc, char** argv) {
    Ast               ast { };

    auto exitWithErrors = [&ast]() {
        for (auto& error : ast.errors)
            cerr << "  " << error << endl;
        return 1;
    };

    for (auto filename : inputFiles) {
        vector<Token> tokens { };
        ifstream          in { filename };
        string    characters { istreambuf_iterator<char>(in), istreambuf_iterator<char>() };

        cerr << "Parsing " << filename << endl;

        parseTokens(filename, characters, tokens, ast.errors);
        if (!empty(ast.errors)) return exitWithErrors();

        parseGrammar(tokens, ast);
        if (!empty(ast.errors)) return exitWithErrors();
    }

    findAllTheThings(ast);
    if (!empty(ast.errors)) return exitWithErrors();

    cout << ast << endl;

    generateTheCode(ast, std::cout);

    return 0;
}
