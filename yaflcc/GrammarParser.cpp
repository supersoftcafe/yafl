//
// Created by Michael Brown on 19/03/2022.
//

#include "GrammarParser.h"
#include "Tools.h"

#include <iostream>
#include <numeric>
#include <span>
#include <algorithm>

using namespace std;
using namespace ast;


struct GrammarParser {
    Ast& ast;

    ParseState<bool> parseModule(Tokens tk);
};


static vector<string> fail(Tokens tokens, char const * message) {
    if (tokens.empty()) return { "end of file" };
    return { to_string(tokens.front().line) + ':' + to_string(tokens.front().character) + ' ' + message };
}

template <class T> static vector<string> fail(ParseState<T> state, Tokens tokens, char const * message) {
    vector<string> errors = state.errors();
    if (tokens.empty()) errors.emplace_back("end of file");
    errors.emplace_back(to_string(tokens.front().line) + ':' + to_string(tokens.front().character) + ' ' + message);
    return errors;
}

static string join(span<string> strings, string const & separator) {
    if (size(strings) == 0) return {};
    else if (size(strings) == 1) return strings[0];
    else return strings[0] + separator + join(strings.subspan(1), separator);
}

static ParseState<vector<string>> parseDottyName(Tokens tk) {
    vector<string> names;

    auto name = getToken(tk);
    if (name.result()->kind != Token::NAME)
        return fail(name, "Expected NAME token");
    tk = name;

    names.emplace_back(name.result()->text);

    for (;;) {
        auto dot = getToken(tk);
        if (dot.result()->kind != Token::DOT)
            return { tk, move(names) };
        tk = dot;

        name = getToken(tk);
        if (name.result()->kind != Token::NAME)
            return fail(name, "Expected NAME token");
        tk = name;

        names.emplace_back(name.result()->text);
    }
}

static ParseState<string> parseModuleName(Tokens tk) {
    auto r1 = getToken(tk);
    if (r1.result()->kind != Token::MODULE)
        return fail(r1, "Expected MODULE token");

    auto r2 = parseDottyName(r1);
    if (!r2.has_result())
        return fail(move(r2), tk, "Expected a module name");

    return { r2, join(span(r2.result()), ".") };
}

static ParseState<TypeRef> parseTypeRef(Tokens tk) {
    auto namesResult = parseDottyName(tk);
    if (!namesResult.has_result())
        return move(namesResult.errors());
    tk = namesResult;
    auto& names = namesResult.result();

    if (size(names) > 1) {
        return { tk, { .moduleName = join(span(names).subspan(0, size(names)-1), ".") , .typeName = names.back() }};
    } else {
        return { tk, { .typeName = names.back() }};
    }
}




static ParseState<unique_ptr<Expression>> justValue(Tokens tk) {
    auto token = getToken(tk);
    tk = token;

    auto text = token.result()->text;
    switch (token.result()->kind) {
        case Token::INTEGER:
            return { tk, make_unique<Expression>(Expression::INTEGER, string(text)) };

        case Token::FLOAT:
            return { tk, make_unique<Expression>(Expression::FLOAT, string(text)) };

        case Token::STRING:
            return { tk, make_unique<Expression>(Expression::FLOAT, string(text.substr(1, text.size() - 2))) };

        case Token::NAME:
            return { tk, make_unique<Expression>(Expression::NAME, string(text)) };

        default:
            return fail(tk, "Expected name or number here");
    }
}

typedef function<ParseState<unique_ptr<Expression>>(Tokens)> ParseExprFunc;
typedef vector<pair<Token::KIND, string>> OpsVector;

static ParseState<unique_ptr<Expression>> parseUnaryExpr(Tokens tk, OpsVector const & opsVec, ParseExprFunc const & nextExpression) {
    auto token = getToken(tk);
    if (!token.has_result())
        return nextExpression(tk);

    auto found = find_if(begin(opsVec), end(opsVec), [&token](auto& op){return op.first == token.result()->kind;});
    if (found == end(opsVec))
        return nextExpression(tk);

    auto rhs = nextExpression(token);
    if (!rhs.has_result())
        return nextExpression(tk);
    tk = rhs;

    vector<unique_ptr<Expression>> params;
    params.emplace_back(make_unique<Expression>(Expression::NAME, string(found->second)));
    params.emplace_back(move(rhs.result()));

    return { tk, make_unique<Expression>(Expression::CALL, move(params)) };
}

static ParseState<unique_ptr<Expression>> parseBinaryExpr(Tokens tk, OpsVector const & opsVec, ParseExprFunc const & nextExpression) {
    auto lhs = nextExpression(tk);
    if (!lhs.has_result())
        return lhs;
    tk = lhs;

    for (;;) {
        auto token = getToken(tk);
        if (!token.has_result())
            return move(lhs);
        tk = token;

        auto found = find_if(begin(opsVec), end(opsVec), [&token](auto& op){return op.first == token.result()->kind;});
        if (found == end(opsVec))
            return move(lhs);

        auto rhs = nextExpression(tk);
        if (!rhs.has_result())
            return move(lhs);
        tk = rhs;

        vector<unique_ptr<Expression>> params;
        params.emplace_back(make_unique<Expression>(Expression::NAME, string(found->second)));
        params.emplace_back(move(lhs.result()));
        params.emplace_back(move(rhs.result()));

        lhs.emplace(tk, make_unique<Expression>(Expression::CALL, move(params)));
    }
}

static ParseState<unique_ptr<Expression>> parseTernaryExpr(Tokens tk, string const & opName, Token::KIND firstKind, Token::KIND secondKind, ParseExprFunc const & nextExpression) {
    auto lhs = nextExpression(tk);
    if (!lhs.has_result())
        return lhs;
    tk = lhs;

    auto firstToken = getToken(tk);
    if (!firstToken.has_result() || firstToken.result()->kind != firstKind)
        return move(lhs);
    tk = firstToken;

    auto middle = parseTernaryExpr(tk, opName, firstKind, secondKind, nextExpression);
    if (!middle.has_result())
        return move(lhs);
    tk = middle;

    auto secondToken = getToken(tk);
    if (!secondToken.has_result() || secondToken.result()->kind != secondKind)
        return move(lhs);
    tk = secondToken;

    auto rhs = parseTernaryExpr(tk, opName, firstKind, secondKind, nextExpression);
    if (!rhs.has_result())
        return move(rhs);
    tk = rhs;

    vector<unique_ptr<Expression>> params;
    params.emplace_back(make_unique<Expression>(Expression::NAME, opName));
    params.emplace_back(move(lhs.result()));
    params.emplace_back(move(middle.result()));
    params.emplace_back(move(rhs.result()));

    return { tk, make_unique<Expression>(Expression::CALL, move(params))};
}

auto parseExpression =
        ParseExprFunc{bind(parseTernaryExpr, placeholders::_1, "`?:`", Token::QUESTION, Token::COLON,
        ParseExprFunc{bind(parseBinaryExpr, placeholders::_1, OpsVector{ {Token::OR , "`|`" } },
        ParseExprFunc{bind(parseBinaryExpr, placeholders::_1, OpsVector{ {Token::XOR, "`^`" } },
        ParseExprFunc{bind(parseBinaryExpr, placeholders::_1, OpsVector{ {Token::AND, "`&`" } },
        ParseExprFunc{bind(parseBinaryExpr, placeholders::_1, OpsVector{ {Token::EQ , "`=`" }, {Token::NEQ , "`!=`"} },
        ParseExprFunc{bind(parseBinaryExpr, placeholders::_1, OpsVector{ {Token::LT , "`<`" }, {Token::LTE , "`<=`"}, {Token::GTE , "`>=`" }, {Token::GT, "`>`" } },
        ParseExprFunc{bind(parseBinaryExpr, placeholders::_1, OpsVector{ {Token::SHL, "`<<`"}, {Token::ASHR, "`>>`"}, {Token::LSHR, "`>>>`"} },
        ParseExprFunc{bind(parseBinaryExpr, placeholders::_1, OpsVector{ {Token::ADD, "`+`" }, {Token::SUB , "`-`" } },
        ParseExprFunc{bind(parseBinaryExpr, placeholders::_1, OpsVector{ {Token::MUL, "`*`" }, {Token::DIV , "`/`" }, {Token::REM , "`%`"  } },
        ParseExprFunc{bind(parseUnaryExpr , placeholders::_1, OpsVector{ {Token::ADD, "`+`" }, {Token::SUB , "`-`" }, {Token::NOT , "`!`"  } },
        ParseExprFunc{justValue}
)})})})})})})})})})};





static ParseState<unique_ptr<Function>> parseFunctionPrototype(Tokens tk, span<ScopeContext> scope = { }) {
    auto name = getToken(tk);
    if (name.result()->kind != Token::NAME)
        return fail(name, "Expected NAME token");
    tk = name;

    auto fn = make_unique<Function>();
    fn->name = name.result()->text;
    fn->scope = scope;

    auto oangle = getToken(tk);
    if (oangle.result()->kind == Token::LT) {
        tk = oangle;

        bool commaRequired = false;
        for (;;) {
            auto cangle = getToken(tk);
            if (cangle.result()->kind == Token::GT) {
                tk = cangle;
                break;
            }

            if (commaRequired) {
                auto comma = getToken(tk);
                if (comma.result()->kind != Token::COMMA)
                    return fail(comma, "Expected COMMA token");
                tk = comma;
            } commaRequired = true;

            // TODO: Parse actual generic constraint
            auto param = getToken(tk);
            if (param.result()->kind != Token::NAME)
                return fail(param, "Expected NAME token");
            tk = param;

            fn->genericParameters.emplace_back(GenericParam{.name = param.result()->text });
        }
    }

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
                return move(param);
            tk = param;

            fn->parameters.push_back(move(param.result()));
        }
    }

    auto colon = getToken(tk);
    if (colon.result()->kind != Token::COLON)
        return fail(colon, "Expected COLON token");
    tk = colon;

    auto type = parseTypeRef(tk);
    if (!type.has_result())
        return move(type.errors());
    tk = type;
    fn->result = move(type.result());

    auto equals = getToken(tk);
    if (equals.result()->kind == Token::EQ) {
        tk = equals;
        auto expr = parseExpression(tk);
        if (!expr.has_result())
            return move(expr.errors());
        tk = expr;

        fn->body = move(expr.result());
    }

    return { tk, move(fn) };
}

static ParseState<unordered_set<string>> parseAnnotations(Tokens tk) {
    auto token = getToken(tk);
    if (token.result()->kind != Token::AT)
        return { tk, unordered_set<string>() };

    auto name = getToken(token);
    if (name.result()->kind != Token::NAME)
        return fail(tk, "Expected annotation");

    auto result = parseAnnotations(name);
    if (result.has_result()) {
        auto& set = result.result();
        set.insert(move(name.result()->text));
        return { result, move(set) };
    } else {
        return fail(result, tk, "Bad annotation");
    }
}

static ParseState<unique_ptr<Function>> parseFunction(Tokens tk, span<ScopeContext> scope) {
    auto token = getToken(tk);
    if (token.result()->kind != Token::FUN)
        return { }; // No error and no result
    tk = token;

    auto annotations = parseAnnotations(tk);
    if (annotations.has_errors())
        return fail(annotations, tk, "Bad annotations");
    tk = annotations;

    auto funProto = parseFunctionPrototype(tk, scope);
    if (funProto.has_result())
        exchange(funProto.result()->annotations, annotations.result());
    return funProto;
}

static ParseState<vector<ScopeContext>> parseScope(Tokens tk) {
    vector<ScopeContext> imports;

    imports.emplace_back(ScopeContext{.moduleName = "System" });

    for (;;) {
        auto token = getToken(tk);
        if (token.result()->kind != Token::USE)
            return { tk, move(imports) };

        auto nameResult = parseDottyName(tk);
        if (!nameResult.has_result())
            return fail(nameResult, "use keyword without import name");
        tk = nameResult;

        auto& name = nameResult.result();
        imports.emplace_back(ScopeContext{.moduleName = join(span(name), ".")});
    }
}

ParseState<bool> GrammarParser::parseModule(Tokens tk) {
    auto moduleName = parseModuleName(tk);
    if (!moduleName.has_result())
        return fail(move(moduleName), tk, "Module declaration is required");
    tk = moduleName;

    auto module = ast.findOrCreateModule(moduleName.result());

    auto scopeResult = parseScope(tk);
    if (!scopeResult.has_result())
        return move(scopeResult.errors());
    tk = scopeResult;

    module->scopes.emplace_back(move(scopeResult.result()));
    span<ScopeContext> scope = module->scopes.back();

    for (;;) {
        auto state = parseFunction(tk, scope);
        if (state.has_errors())
            return move(state.errors());
        if (!state.has_result()) // There are no more functions. End search.
            return { tk, true };
        tk = state;

        module->functions.emplace_back(move(state.result()));
    }
}

void parseGrammar(Tokens tk, Ast& ast) {
    GrammarParser parser { .ast = ast };

    while (peekToken(tk)->kind != Token::EOI) {
        auto result = parser.parseModule(tk);

        if (result.has_errors()) {
            ast.errors += result.errors();
            return;
        }

        if (!result.has_result()) {
            ast.errors += string{"No module found but not at end of input"};
            return;
        }

        tk = result;
    }
}
