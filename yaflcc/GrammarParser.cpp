//
// Created by Michael Brown on 19/03/2022.
//

#include "GrammarParser.h"
#include <iostream>

using namespace std;

GrammarParser::GrammarParser() = default;
GrammarParser::~GrammarParser() = default;

template <class T>
static ParseState<T> fail(Tokens tokens, char const * message) {
    if (tokens.empty()) cerr << "end of file" << endl;
    else cerr << tokens.front().line << ':' << tokens.front().character << ' ' << message << endl;
    return { };
}

static ParseState<vector<string>> parseDottyName(Tokens tk) {
    std::vector<string> names;

    auto name = getToken(tk, Token::NAME); if (!name) return { };
    names.emplace_back(name.result()->text);

    for (;;) {
        auto dot = getToken(name, Token::DOT); if (!dot) return { name, std::move(names) };
        name = getToken(dot, Token::NAME); if (!name) return { };
        names.emplace_back(name.result()->text);
    }
}

static ParseState<vector<string>> parseModuleName(Tokens tk) {
    auto r1 = getToken(tk, Token::MODULE); if (!r1) return { };
    auto r2 = parseDottyName(r1); if (!r2) return { };
    return { r2, std::move(r2.result()) };
}

static ParseState<ast::TypeRef> parseTypeRef(Tokens tk) {
    auto names = parseDottyName(tk);
    ast::TypeRef td { .names = std::move(names.result()) };
    return { names, td };
}

static ParseState<unique_ptr<ast::Expression>> parseExpression(Tokens tk) {
    auto token = getToken(tk);
    if (!token) return { };

    switch (token.result()->kind) {
        case Token::NUMBER: {
            auto v = make_unique<ast::LiteralValue>();
            v->value = token.result()->text;
            return { token, std::move(v) };
        }
        case Token::NAME: {
            // TODO: Parse expression that names a variable
        }
        default: return { };
    }
}

static ParseState<unique_ptr<ast::Function>> parseFunction(Tokens tk) {
    auto fun    = getToken(tk  , Token::FUN   ); if (!fun   ) return { };
    auto name   = getToken(fun , Token::NAME  ); if (!name  ) return { };
    // TODO: Parse the optional parameters
    auto colon  = getToken(name, Token::COLON ); if (!colon ) return { };
    // TODO: Return type should be converted to a type reference
    auto type   = parseTypeRef(colon);           if (!type  ) return { };
    auto equals = getToken(type, Token::EQUALS); if (!equals) return { };
    auto expr   = parseExpression(equals      ); if (!expr  ) return { };

    auto fn = make_unique<ast::Function>();
    fn->name = name.result()->text;
    // TODO: Set parameters
    // fn->params = ....
    fn->body = std::move(expr.result());

    return { expr, std::move(fn) };
}


ast::Module* GrammarParser::findOrCreateModule(vector<string> const & path) {
    if (ast.root == nullptr)
        ast.root = make_unique<ast::Module>("");
    ast::Module* module = ast.root.operator->();

    for (auto const & name : path) {
        auto found = module->modules.find(name);
        if (found == module->modules.end())
            found = module->modules.insert(std::make_pair(name, make_unique<ast::Module>(name))).first;
        module = found->second.operator->();
    }

    return module;
}

ParseState<bool> GrammarParser::parseModule(Tokens tk) {
    auto moduleName = parseModuleName(tk);
    if (!moduleName) return fail<bool>(moduleName, "missing module declaration");
    tk = moduleName;

    auto module = findOrCreateModule(moduleName.result());

//    auto imports = parseImports(tk);
//    if (imports) {
//        tk = imports;
//
//    }

    for (;;) {
        auto state = parseFunction(tk);
        if (!state) return { tk, true };
        tk = state;

        auto name = state.result()->name;
        module->functions.insert_or_assign(name, std::move(state.result()));
    }
}

ParseState<bool> GrammarParser::parseFile(Tokens tk) {
    while (!tk.empty()) {
        auto result = parseModule(tk);
        if (!result) fail<bool>(result, "no module :(");
        tk = result;
    }

    return { tk, true };
}
