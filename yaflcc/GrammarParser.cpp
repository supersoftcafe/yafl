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



static vector<string> fail(Tokens tokens, char const *message) {
    if (tokens.empty()) return {"end of file"};
    auto& source = tokens.front().source;
    return {to_string(source.line) + ':' + to_string(source.character) + ' ' + message};
}

template<class T>
static vector<string> fail(ParseState<T> state, Tokens tokens, char const *message) {
    vector<string> errors = state.errors();
    if (tokens.empty()) errors.emplace_back("end of file");
    auto& source = tokens.front().source;
    errors.emplace_back(to_string(source.line) + ':' + to_string(source.character) + ' ' + message);
    return errors;
}

static string join(span<string> strings, string const &separator) {
    if (size(strings) == 0) return {};
    else if (size(strings) == 1) return strings[0];
    else return strings[0] + separator + join(strings.subspan(1), separator);
}

template <typename TInt> static bool inRange(int64_t intValue) {
    return intValue >= int64_t(numeric_limits<TInt>::min()) && intValue <= int64_t(numeric_limits<TInt>::max());
}


struct GrammarParser {
    Ast &ast;


    ParseState<vector<string>> parseDottyName(Tokens tk) {
        vector<string> names;

        auto name = getToken(tk);
        if (name.result()->kind != Token::NAME)
            return fail(name, "Expected NAME token");
        tk = name;

        names.emplace_back(name.result()->text);

        for (;;) {
            auto dot = getToken(tk);
            if (dot.result()->kind != Token::DOT)
                return {tk, move(names)};
            tk = dot;

            name = getToken(tk);
            if (name.result()->kind != Token::NAME)
                return fail(name, "Expected NAME token");
            tk = name;

            names.emplace_back(name.result()->text);
        }
    }

    ParseState<string> parseModuleName(Tokens tk) {
        auto r1 = getToken(tk);
        if (r1.result()->kind != Token::MODULE)
            return fail(tk, "Expected MODULE token");

        auto r2 = parseDottyName(r1);
        if (!r2.has_result())
            return fail(move(r2), tk, "Expected a module name");

        return {r2, join(span(r2.result()), ".")};
    }

    ParseState<Named> parseNamedType(Tokens tk) {
        auto namesResult = parseDottyName(tk);
        if (!namesResult.has_result())
            return move(namesResult.errors());
        tk = namesResult;
        auto &names = namesResult.result();

        if (size(names) > 1) {
            auto module = ast.findOrCreateModule(join(span(names).subspan(0, size(names) - 1), "."));
            return {tk, Named{ .typeName = names.back(), .module = module , .declaration = nullptr }};
        } else {
            return {tk, Named{ .typeName = names.back(), .module = nullptr, .declaration = nullptr }};
        }
    }

    ParseState<Tuple> parseTupleType(Tokens tk) {
        auto open = getToken(tk);
        if (open.result()->kind != Token::OBRACKET)
            return {};
        tk = open;

        Tuple tuple;
        int count = 0;
        bool needsComma = false;
        while (peekToken(tk)->kind != Token::CBRACKET) {
            auto name = "value" + to_string(++count);

            // Comma or bracket
            if (needsComma) {
                auto comma = getToken(tk);
                if (comma.result()->kind != Token::COMMA)
                    return fail(tk, "Expected comma or close bracket");
                tk = comma;
            }
            needsComma = true;

            // Is this a named field? Otherwise the default name is left as is.
            auto token = getToken(tk);
            if (token.result()->kind == Token::NAME) {
                // If next is colon, then this really is a name and not a type
                auto colon = getToken(token);
                if (colon.result()->kind == Token::COLON) {
                    name = token.result()->text;
                    tk = colon; // Advance
                }
            }

            // Defo must have a type
            auto nestedType = parseType(tk);
            if (!nestedType.has_result())
                return fail(tk, "Expected a type here");
            tuple.parameters.emplace_back(Parameter{.name = name, .type = move(nestedType.result())});
            tk = nestedType;
        }

        auto close = getToken(tk);
        return {close, move(tuple)};
    }

    ParseState<Function> parseFunctionType(Tokens tk) {
        auto tuple = parseTupleType(tk);
        if (!tuple.has_result())
            return { };
        tk = tuple;

        auto colon = getToken(tk);
        if (colon.result()->kind != Token::COLON)
            return { };
        tk = colon;

        auto result = parseType(tk);
        if (!result.has_result())
            return { };
        tk = result;

        return {tk, Function{.parameter = move(tuple.result()), .result = {move(result.result())} } };
    }


    ParseState<Type> parseType(Tokens tk) {
        auto n = parseNamedType(tk);
        if (n.has_result())
            return {n, Type{.type{move(n.result())}}};

        auto f = parseFunctionType(tk);
        if (f.has_result())
            return {f, Type{.type{move(f.result())}}};

        auto t = parseTupleType(tk);
        if (t.has_result())
            return {t, Type{.type{move(t.result())}}};

        if (n.has_errors())
            return move(n.errors());
        if (f.has_errors())
            return move(f.errors());
        return move(t.errors());
    }

    ParseState<forward_list<Expression>> parseParameters(Tokens tk) {
        auto obracket = getToken(tk);
        if (obracket.result()->kind != Token::OBRACKET)
            return { };
        tk = obracket;

        bool needsComma = false;
        forward_list<Expression> params;
        auto previousPosition = params.before_begin();

        while (peekToken(tk)->kind != Token::CBRACKET) {
            if (needsComma) {
                auto comma = getToken(tk);
                if (comma.result()->kind != Token::COMMA)
                    return fail(tk, "expected comma");
                tk = comma;
            }
            needsComma = true;

            auto expr = parseExpression(tk);
            if (expr.has_errors())
                return { move(expr.errors()) };
            else if (!expr.has_result())
                return fail(tk, "expected expression as parameter");
            tk = expr;

            previousPosition = params.emplace_after(previousPosition, move(expr.result()));
        }
        tk = getToken(tk); // Guaranteed to be ')', so consume it

        return { tk, move(params) };
    }

    ParseState<Expression> parseIntrinsic(Tokens tk, int nextLevel) {
        auto intrinsic = getToken(tk);
        if (intrinsic.result()->kind != Token::INTRINSIC)
            return parseExpression(tk, nextLevel);
        tk = intrinsic;

        auto name = getToken(tk);
        if (name.result()->kind != Token::NAME)
            return fail(tk, "expected name");
        tk = name;

        auto params = parseParameters(tk);
        if (params.has_errors())
            return { move(params.errors()) };
        else if (!params.has_result())
            return fail(tk, "expected parameters");
        tk = params;

        return {tk, Expression{ .source = intrinsic.result()->source, .op = Intrinsic {
            .name = name.result()->text,
            .parameters = move(params.result())
        }}};
    }

    ParseState<Expression> justValue(Tokens tk) {
        auto token = getToken(tk);

        auto text = token.result()->text;
        switch (token.result()->kind) {
            case Token::INTEGER:
                text.erase(remove(begin(text), end(text), '_'), end(text));
                try {
                    auto base = text.starts_with("0b") ? 2 : (text.starts_with("0o") ? 8 : (text.starts_with("0x") ? 16 : 10));
                    auto type = text.ends_with("i1") ? ast.typeInt8 : (text.ends_with("i2") ? ast.typeInt16 : (text.ends_with("i8") ? ast.typeInt64 : ast.typeInt32));
                    if (base == 10) return {token, Expression{.type = type, .op = stoll(text, nullptr, 10)}};
                    return {token, Expression{ .source = token.result()->source, .type = type, .op = (int64_t)stoull(text.substr(2), nullptr,  base)}};
                } catch (out_of_range const &e) {
                    return fail(tk, "Invalid string literal");
                }

            case Token::FLOAT:
                return {token, Expression{ .source = token.result()->source, .type = text.ends_with("f4") ? ast.typeFloat32 : ast.typeFloat64, .op = stod(text)}};

//            case Token::STRING:
//                return { token, Expression{.type = ast.typeString, .op = text.substr(1, text.size() - 2) } };

            case Token::NAME:
                return {token, Expression{ .source = token.result()->source, .op = LoadVariable { .fieldName = text, .variable = nullptr } } };

            default:
                return fail(tk, "Expected name or number here");
        }
    }

    typedef function<ParseState<Expression>(Tokens)> ParseExprFunc;
    typedef vector<pair<Token::KIND, string>> OpsVector;

    ParseState<Expression> parseUnaryExpr(
            Tokens tk, int nextLevel, OpsVector const & opsVec) {
        auto token = getToken(tk);
        if (!token.has_result())
            return parseExpression(tk, nextLevel);

        auto found = find_if(begin(opsVec), end(opsVec), [&token](auto &op) { return op.first == token.result()->kind; });
        if (found == end(opsVec))
            return parseExpression(tk, nextLevel);

        auto rhs = parseExpression(token, nextLevel);
        if (!rhs.has_result())
            return parseExpression(tk, nextLevel);
        tk = rhs;

        return {tk, Expression{ .source = rhs.result().source, .op = Call{
            .base = { { .source = rhs.result().source, .op = LoadVariable{.fieldName = found->second, .variable = nullptr } } },
            .parameters = {
                move(rhs.result())
        } } } };
    }

    ParseState<Expression> parseBinaryExpr(
            Tokens tk, int nextLevel, OpsVector const & opsVec) {
        auto lhs = parseExpression(tk, nextLevel);
        if (!lhs.has_result())
            return lhs;
        tk = lhs;

        for (;;) {
            auto token = getToken(tk);
            if (!token.has_result())
                return move(lhs);
            tk = token;

            auto found = find_if(begin(opsVec), end(opsVec),
                                 [&token](auto &op) { return op.first == token.result()->kind; });
            if (found == end(opsVec))
                return move(lhs);

            auto rhs = parseExpression(tk, nextLevel);
            if (!rhs.has_result())
                return move(lhs);
            tk = rhs;

            return {tk, Expression{ .source = lhs.result().source, .op = Call{
                .base = { { .source = lhs.result().source, .op = LoadVariable{.fieldName = found->second, .variable = nullptr } } },
                .parameters = {
                    move(lhs.result()),
                    move(rhs.result())
            } } } };
        }
    }

    ParseState<Expression> parseTernaryExpr(
            Tokens tk, int nextLevel, string const &opName, Token::KIND firstKind, Token::KIND secondKind) {
        auto lhs = parseExpression(tk, nextLevel);
        if (!lhs.has_result())
            return lhs;
        tk = lhs;

        auto firstToken = getToken(tk);
        if (!firstToken.has_result() || firstToken.result()->kind != firstKind)
            return move(lhs);
        tk = firstToken;

        auto middle = parseTernaryExpr(tk, nextLevel, opName, firstKind, secondKind);
        if (!middle.has_result())
            return move(lhs);
        tk = middle;

        auto secondToken = getToken(tk);
        if (!secondToken.has_result() || secondToken.result()->kind != secondKind)
            return move(lhs);
        tk = secondToken;

        auto rhs = parseTernaryExpr(tk, nextLevel, opName, firstKind, secondKind);
        if (!rhs.has_result())
            return move(rhs);
        tk = rhs;

        return {tk, Expression{ .source = lhs.result().source, .op = Condition{.parameters = {
                move(lhs.result()),
                move(middle.result()),
                move(rhs.result())
        }}}};

//        return {tk, Expression{ .source = lhs.result().source, .op = Call{
//            .base = { { .source = lhs.result().source, .op = LoadVariable{.fieldName = opName, .variable = nullptr } } },
//            .parameters = {
//                move(lhs.result()),
//                move(middle.result()),
//                move(rhs.result())
//        } } } };
    }

    ParseState<Expression> parseExpression(Tokens tk, int level = 0) {
        switch (level) {
            case 0:return parseTernaryExpr(tk, level + 1, "`?:`", Token::QUESTION, Token::COLON);
            case 1: return parseBinaryExpr(tk, level + 1, {{Token::OR,   "`|`"}});
            case 2: return parseBinaryExpr(tk, level + 1, {{Token::XOR,  "`^`"}});
            case 3: return parseBinaryExpr(tk, level + 1, {{Token::AND,  "`&`"}});
            case 4: return parseBinaryExpr(tk, level + 1, {{Token::EQ,   "`=`"}, {Token::NEQ,  "`!=`"}});
            case 5: return parseBinaryExpr(tk, level + 1, {{Token::LT,   "`<`"}, {Token::LTE,  "`<=`"}, {Token::GTE,   "`>=`"}, {Token::GT,  "`>`"}});
            case 6: return parseBinaryExpr(tk, level + 1, {{Token::SHL, "`<<`"}, {Token::ASHR, "`>>`"}, {Token::LSHR, "`>>>`"}});
            case 7: return parseBinaryExpr(tk, level + 1, {{Token::ADD,  "`+`"}, {Token::SUB,   "`-`"}});
            case 8: return parseBinaryExpr(tk, level + 1, {{Token::MUL,  "`*`"}, {Token::DIV,   "`/`"}, {Token::REM,    "`%`"}});
            case 9: return parseUnaryExpr( tk, level + 1, {{Token::ADD,  "`+`"}, {Token::SUB,   "`-`"}, {Token::NOT,    "`!`"}});
            case 10: return parseIntrinsic(tk, level + 1);
            default: return justValue(tk);
        }
    }

    ParseState<Variable> parseLet(Tokens tk, ScopeContext* scope = nullptr) {
        auto let = getToken(tk);
        if (let.result()->kind != Token::LET)
            return { }; // Not a let expression
        tk = let;

        auto name = getToken(tk);
        if (name.result()->kind != Token::NAME)
            return fail(tk, "Expected NAME token");
        tk = name;

        Type type;
        auto colon = getToken(tk);
        if (colon.result()->kind == Token::COLON) {
            auto rtype = parseType(tk);
            if (!rtype.has_result())
                return fail(rtype, tk, "Expected type");
            type = move(rtype.result());
            tk = rtype;
        }

        auto expr = parseExpression(tk);
        if (!expr.has_result())
            return fail(expr, tk, "Expected expression");
        tk = expr;

        return {tk, {
            .source = let.result()->source,
            .scope = scope,
            .name = move(name.result()->text),
            .type = move(type),
            .value = move(expr.result())
        }};
    }

    ParseState<Variable> parseFun(Tokens tk, ScopeContext* scope = nullptr) {
        auto fun = getToken(tk);
        if (fun.result()->kind != Token::FUN)
            return { }; // Not a function declaration
        tk = fun;

        auto name = getToken(tk);
        if (name.result()->kind != Token::NAME)
            return fail(name, "Expected NAME token");
        tk = name;

        auto type = parseFunctionType(tk);
        if (!type.has_result())
            return fail(type, name, "Expected function type");
        tk = type;

        forward_list<Variable> parameters;
        auto& typeParams = type.result().parameter.parameters;
        for (auto it = rbegin(typeParams); it != rend(typeParams); it++)
            parameters.emplace_front(Variable{.scope = nullptr, .name = it->name, .type = it->type });

        auto equals = getToken(tk);
        if (equals.result()->kind != Token::EQ)
            return fail(type, "Expected equals");
        tk = equals;

        auto expr = parseExpression(tk);
        if (!expr.has_result())
            return fail(expr, tk, "Expected expression");
        tk = expr;

        return {tk, {
            .source = fun.result()->source,
            .scope = scope,
            .name = move(name.result()->text),
            .type = Type{.type = type.result()}, // Copy because it is duplicated into the lambda as well
            .value = Expression{.type = Type{.type = type.result()}, .op = Lambda{.parameters = move(parameters), .body = {move(expr.result())}}}
        }};
    }

    ParseState<unordered_set<string>> parseAnnotations(Tokens tk) {
        auto token = getToken(tk);
        if (token.result()->kind != Token::AT)
            return {tk, unordered_set<string>()};

        auto name = getToken(token);
        if (name.result()->kind != Token::NAME)
            return fail(tk, "Expected annotation");

        auto result = parseAnnotations(name);
        if (result.has_result()) {
            auto &set = result.result();
            set.insert(move(name.result()->text));
            return {result, move(set)};
        } else {
            return fail(result, tk, "Bad annotation");
        }
    }

    ParseState<ScopeContext> parseScope(Tokens tk, Module* owner) {
        ScopeContext imports { .owner = owner, .modules { ast.findOrCreateModule("System") } };

        for (;;) {
            auto token = getToken(tk);
            if (token.result()->kind != Token::USE) {
                imports.modules.push_front(owner); // Owner must always be the first module searched
                return {tk, move(imports)};
            }

            auto nameResult = parseDottyName(tk);
            if (!nameResult.has_result())
                return fail(nameResult, "use keyword without import name");
            tk = nameResult;

            auto &name = nameResult.result();
            imports.modules.push_front(ast.findOrCreateModule(join(span(name), ".")));
        }

    }

    ParseState<monostate> parseModule(Tokens tk) {
        auto moduleName = parseModuleName(tk);
        if (!moduleName.has_result())
            return fail(move(moduleName), tk, "Module declaration is required");
        tk = moduleName;

        auto module = ast.findOrCreateModule(moduleName.result());

        auto scopeResult = parseScope(tk, module);
        if (!scopeResult.has_result())
            return move(scopeResult.errors());
        tk = scopeResult;

        auto scope = &module->scopes.emplace_front(move(scopeResult.result()));

        for (;;) {
            ParseState<Variable> variable = parseFun(tk, scope) | parseLet(tk, scope);
            if (variable.has_errors())
                return move(variable.errors());
            if (!variable.has_result()) // There are no more functions. End search.
                return {tk, monostate{}};
            tk = variable;

            module->variables.emplace_front(move(variable.result()));
        }
    }

};

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
