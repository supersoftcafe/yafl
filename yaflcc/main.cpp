
#include "Token.h"
#include "TokenParser.h"
#include "GrammarParser.h"
#include "TypeResolver.h"
#include "Verifier.h"

#include <iostream>
#include <fstream>
#include <vector>
#include <regex>

using namespace ast;
using namespace std;

void printFunctions(Ast& ast) {
    for (auto& module : ast.modules) {
        cout << endl << "module " << module->name << endl << endl;
        for (auto& function : module->functions) {
            cout << "fun " << function << endl;
        }
    }
}


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

        parseTokens(characters, tokens, ast.errors);
        if (!empty(ast.errors)) return exitWithErrors();

        parseGrammar(tokens, ast);
        if (!empty(ast.errors)) return exitWithErrors();
    }

    printFunctions(ast);

    findAllTheThings(ast);
    if (!empty(ast.errors)) return exitWithErrors();

    verifyAllTheThings(ast);
    if (!empty(ast.errors)) return exitWithErrors();

    return 0;
}
