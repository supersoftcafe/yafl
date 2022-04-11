
#include "Token.h"
#include "TokenParser.h"
#include "GrammarParser.h"
#include "TypeResolver.h"
#include <iostream>
#include <fstream>
#include <vector>
#include <regex>

using namespace std;

void printFunctions(std::string prefix, ast::Module* module) {
    for (auto& function : module->functions) {
        std::cout << prefix << '.' << function << std::endl;
    }
    for (auto& module : module->modules) {
        printFunctions(prefix + '.' + module->name, module.get());
    }
}

int main(int argc, char** argv) {
    auto pwd = std::filesystem::current_path();
    std::ifstream        in { "../yaflcc/samples/02_hello_world2.yafl" };
    TokenParser tokenParser { string(istreambuf_iterator<char>(in), istreambuf_iterator<char>()) };
    ast::Ast ast;

    GrammarParser grammarParser(ast, tokenParser.tokens);
    if (!std::empty(grammarParser.errors)) {
        cerr << "Failed" << endl;
        for (auto& error : grammarParser.errors)
            cerr << "  " << error << endl;
        return 1;
    }

    printFunctions("", ast.root.get());

    TypeResolver typeResolver(ast);
    if (!std::empty(typeResolver.errors)) {
        cerr << "Failed" << endl;
        for (auto& error : typeResolver.errors)
            cerr << "  " << error << endl;
        return 2;
    }

    return 0;
}
