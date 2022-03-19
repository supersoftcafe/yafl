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

static ParseState<string_view> parseModuleName(Tokens tk) {
    auto r1 = getToken(tk, Token::MODULE); if (!r1) return { };
    auto r2 = getToken(r1, Token::NAME  ); if (!r2) return { };
    return { r2, r2.result()->text };
}

static ParseState<ast::TypeDeclaration> parseTypeDeclaration(Tokens tk) {
    ast::TypeDeclaration td;

    auto name = getToken(tk, Token::NAME); if (!name) return { };
    td.qualifiedName.emplace_back(name.result()->text);

    for (;;) {
        auto dot = getToken(name, Token::DOT); if (!dot) return { name, td };
        name = getToken(dot, Token::NAME); if (!name) return { };
        td.qualifiedName.emplace_back(name.result()->text);
    }
}

static ParseState<shared_ptr<ast::Expression>> parseExpression(Tokens tk) {
    auto number = getToken(tk, Token::NUMBER); if (!number) return { };

    auto v = ast::Value::create();
    v->value = number.result()->text;

    return { number, v };
}

static ParseState<shared_ptr<ast::Function>> parseFunction(Tokens tk) {
    auto fun    = getToken(tk  , Token::FUN   ); if (!fun   ) return { };
    auto name   = getToken(fun , Token::NAME  ); if (!name  ) return { };
    auto colon  = getToken(name, Token::COLON ); if (!colon ) return { };
    auto type   = parseTypeDeclaration(colon  ); if (!type  ) return { };
    auto equals = getToken(type, Token::EQUALS); if (!equals) return { };
    auto expr   = parseExpression(equals      ); if (!expr  ) return { };

    auto fn = make_shared<ast::Function>();
    fn->name = name.result()->text;
    fn->body = expr.result();

    return { expr, fn };
}

static ParseState<map<string,shared_ptr<ast::Function>>> parseFunctions(Tokens tk) {
    map<string,shared_ptr<ast::Function>> result;

    for (;;) {
        auto state = parseFunction(tk);
        if (!state) return {tk, result };

        auto fn = state.result();
        tk = state.tokens();

        result.insert_or_assign(fn->name, fn);
    }
}

ParseState<shared_ptr<ast::Ast>> GrammarParser::parse(Tokens tk) {
    auto moduleName = parseModuleName(tk);
    if (!moduleName)
        return fail<shared_ptr<ast::Ast>>(moduleName, "missing module declaration");

    auto functions = parseFunctions(moduleName);
    if (!functions)
        return fail<shared_ptr<ast::Ast>>(moduleName, "missing module declaration");

    auto result = make_shared<ast::Ast>();
    result->name = moduleName.result();
    functions.xfer(result->functions); // Heavy weight map, so use a faster xfer

    return { functions, result };
}
