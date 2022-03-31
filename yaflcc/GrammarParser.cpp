//
// Created by Michael Brown on 19/03/2022.
//

#include "GrammarParser.h"
#include <iostream>
#include <numeric>
#include <algorithm>

using namespace std;

GrammarParser::~GrammarParser() = default;


static vector<string> fail(Tokens tokens, char const * message) {
    if (tokens.empty()) return { "end of file" };
    return { to_string(tokens.front().line) + ':' + to_string(tokens.front().character) + ' ' + message };
}

template <class T> static std::vector<std::string>&& fail(ParseState<T>&& state, Tokens tokens, char const * message) {
    vector<string> errors { std::move(state.errors()) };
    if (tokens.empty()) errors.emplace_back("end of file");
    errors.emplace_back(to_string(tokens.front().line) + ':' + to_string(tokens.front().character) + ' ' + message);
    return std::move(errors);
}

static ParseState<vector<string>> parseDottyName(Tokens tk) {
    std::vector<string> names;

    auto name = getToken(tk);
    if (name.result()->kind != Token::NAME)
        return fail(name, "Expected NAME token");
    tk = name;

    names.emplace_back(name.result()->text);

    for (;;) {
        auto dot = getToken(tk);
        if (dot.result()->kind != Token::DOT)
            return { tk, std::move(names) };
        tk = dot;

        name = getToken(tk);
        if (name.result()->kind != Token::NAME)
            return fail(name, "Expected NAME token");
        tk = name;

        names.emplace_back(name.result()->text);
    }
}

static ParseState<vector<string>> parseModuleName(Tokens tk) {
    auto r1 = getToken(tk);
    if (r1.result()->kind != Token::MODULE)
        return fail(r1, "Expected MODULE token");
    tk = r1;

    auto r2 = parseDottyName(r1);
    tk = r2;
    if (!r2.has_result())
        return fail(std::move(r2), tk, "Expected a module name");
    return { r2, std::move(r2.result()) };
}

static ParseState<ast::TypeRef> parseTypeRef(Tokens tk) {
    auto names = parseDottyName(tk);
    ast::TypeRef td { .names = std::move(names.result()) };
    return { names, td };
}




static ParseState<unique_ptr<ast::Expression>> justValue(Tokens tk) {
    auto token = getToken(tk);
    tk = token;

    ast::LiteralValue::KIND kind;
    switch (token.result()->kind) {
        case Token::NUMBER:
            kind = ast::LiteralValue::NUMBER;
            break;
        case Token::NAME:
            kind = ast::LiteralValue::NAME;
            break;
        default:
            return fail(tk, "Expected name or number here");
    }

    auto v = make_unique<ast::LiteralValue>();
    v->kind = kind;
    v->value = token.result()->text;
    return { tk, std::move(v) };
}

static ParseState<unique_ptr<ast::Expression>> timesDivideModulus(Tokens tk) {
    auto lhs = justValue(tk);
    if (!lhs.has_result())
        return lhs;
    tk = lhs;

    for (;;) {
        auto token = getToken(tk);
        tk = token;

        ast::Binary::KIND kind;
        switch (token.result()->kind) {
            case Token::MUL:
                kind = ast::Binary::MUL;
                break;

            case Token::DIV:
                kind = ast::Binary::DIV;
                break;

            default:
                return std::move(lhs);
        }

        auto rhs = justValue(tk);
        if (!rhs.has_result())
            return std::move(lhs);
        tk = rhs;

        auto expr = make_unique<ast::Binary>();
        expr->kind = kind;
        expr->left = std::move(lhs.result());
        expr->right = std::move(rhs.result());
        lhs.emplace(tk, std::move(expr));
    }
}

static ParseState<unique_ptr<ast::Expression>> plusMinus(Tokens tk) {
    auto lhs = timesDivideModulus(tk);
    if (!lhs.has_result())
        return lhs;
    tk = lhs;

    for (;;) {
        auto token = getToken(tk);
        if (!token.has_result())
            return std::move(lhs);
        tk = token;

        ast::Binary::KIND kind;
        switch (token.result()->kind) {
            case Token::ADD:
                kind = ast::Binary::ADD;
                break;

            case Token::SUB:
                kind = ast::Binary::SUB;
                break;

            default:
                return std::move(lhs);
        }

        auto rhs = timesDivideModulus(tk);
        if (!rhs.has_result())
            return std::move(lhs);
        tk = rhs;

        auto expr = make_unique<ast::Binary>();
        expr->kind = kind;
        expr->left = std::move(lhs.result());
        expr->right = std::move(rhs.result());
        lhs.emplace(tk, std::move(expr));
    }
}

static ParseState<unique_ptr<ast::Expression>> parseExpression(Tokens tk) {
    return plusMinus(tk);
}


static ParseState<unique_ptr<ast::Function>> parseFunctionPrototype(Tokens tk) {
    auto name = getToken(tk);
    if (name.result()->kind != Token::NAME)
        return fail(name, "Expected NAME token");
    tk = name;


    auto fn = make_unique<ast::Function>();
    fn->name = name.result()->text;

    auto obracket = getToken(tk);
    if (obracket.result()->kind == Token::OBRACKET) {
        tk = obracket;

        bool commaRequired = false;
        for (;;) {
            auto cbracket = getToken(tk);
            if (cbracket.result()->kind == Token::CBRACKET) {
                tk = cbracket;
                break;
            }

            if (commaRequired) {
                auto comma = getToken(tk);
                if (comma.result()->kind != Token::COMMA)
                    return fail(comma, "Expected COMMA token");
                tk = comma;
            } commaRequired = true;

            auto param = parseFunctionPrototype(tk);
            if (!param.has_result())
                return std::move(param);
            tk = param;

            fn->params.push_back(std::move(param.result()));
        }
    }

    auto colon = getToken(tk);
    if (colon.result()->kind != Token::COLON)
        return fail(colon, "Expected COLON token");
    tk = colon;

    auto type = parseTypeRef(tk);
    if (!type.has_result())
        return std::move(type.errors());
    tk = type;
    fn->result = std::move(type.result());

    auto equals = getToken(tk);
    if (equals.result()->kind == Token::EQ) {
        tk = equals;
        auto expr = parseExpression(tk);
        if (!expr.has_result())
            return std::move(expr.errors());
        tk = expr;

        fn->body = std::move(expr.result());
    }

    return { tk, std::move(fn) };
}

static ParseState<unique_ptr<ast::Function>> parseFunction(Tokens tk) {
    auto fun = getToken(tk);
    if (fun.result()->kind != Token::FUN)
        return { }; // No error and no result
    return parseFunctionPrototype(fun);
}

ParseState<bool> GrammarParser::parseModule(Tokens tk) {
    auto moduleName = parseModuleName(tk);
    if (!moduleName.has_result())
        return fail(std::move(moduleName), tk, "Module declaration is required");
    tk = moduleName;

    auto module = ast.findOrCreateModule(moduleName.result());

//    auto imports = parseImports(tk);
//    if (imports) {
//        tk = imports;
//
//    }

    for (;;) {
        auto state = parseFunction(tk);
        if (state.has_errors())
            return std::move(state.errors());
        if (!state.has_result()) // There are no more functions. End search.
            return { tk, true };
        tk = state;

        auto name = state.result()->name;
        module->functions.insert_or_assign(name, std::move(state.result()));
    }
}

GrammarParser::GrammarParser(ast::Ast& ast, Tokens tk) : ast(ast) {
    while (peekToken(tk)->kind != Token::EOI) {
        auto result = parseModule(tk);

        if (result.has_errors()) {
            errors = std::move(result.errors());
            break;
        }

        if (!result.has_result()) {
            errors.emplace_back("No module found but not at end of input");
            break;
        }

        tk = result;
    }
}
