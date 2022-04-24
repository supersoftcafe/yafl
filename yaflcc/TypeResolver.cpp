//
// Created by Michael Brown on 27/03/2022.
//

#include "TypeResolver.h"
#include "Tools.h"

using namespace ast;
using namespace std;

struct TypeResolver {
    Ast& ast;
    vector<std::string>& errors;

    TypeResolver(Ast& ast, vector<std::string>& errors) : ast(ast), errors(errors) { }


    template <typename TInt> static bool checkRange(int64_t intValue) {
        return intValue < numeric_limits<TInt>::min() || intValue > numeric_limits<TInt>::max();
    }


    TypeDef* resolveInteger(Expression* expression, TypeDef* receiverIfKnown) {
        if (expression->type == nullptr) {
            string stringValue = expression->value;
            stringValue.erase(remove(begin(stringValue), end(stringValue), '_'), end(stringValue));

            bool isSigned = false;
            int64_t intValue;

            try {
                if (stringValue.starts_with("0b")) {
                    // Binary unsigned
                    intValue = int64_t(stoull(stringValue, nullptr, 2));
                } else if (stringValue.starts_with("0o")) {
                    // Octal unsigned
                    intValue = int64_t(stoull(stringValue, nullptr, 8));
                } else if (stringValue.starts_with("0x")) {
                    // Hex unsigned
                    intValue = int64_t(stoull(stringValue, nullptr, 16));
                } else {
                    // Decimal signed
                    isSigned = true;
                    intValue = stoll(stringValue, nullptr, 10);
                }
            } catch (out_of_range const &e) {
                ast.errors.push_back("Invalid string literal");
                return nullptr;
            }

            if (isSigned ? checkRange<int8_t>(intValue) : checkRange<uint8_t>(intValue))
                expression->type = ast.typeInt8;
            else if (isSigned ? checkRange<int16_t>(intValue) : checkRange<uint16_t>(intValue))
                expression->type = ast.typeInt16;
            else if (isSigned ? checkRange<int32_t>(intValue) : checkRange<uint32_t>(intValue))
                expression->type = ast.typeInt32;
            else
                expression->type = ast.typeInt64;
        }

        // Whatever the integer is, if the receiver wants a wider integer, we adjust.
        if (receiverIfKnown == ast.typeInt64) {
            expression->type = receiverIfKnown;
        } else if (receiverIfKnown == ast.typeInt32 && (expression->type == ast.typeInt8 || expression->type == ast.typeInt16)) {
            expression->type = receiverIfKnown;
        } else if (receiverIfKnown == ast.typeInt16 && expression->type == ast.typeInt8) {
            expression->type = receiverIfKnown;
        }

        return expression->type;
    }

    TypeDef* resolveCall(
            Expression* expression,
            function<Function*(function<bool(Function*)>const&)> const & findCandidateFunctions,
            TypeDef* receiverIfKnown) {

        // Get initial idea of parameter types. We don't know receiver types yet.
        for (auto& param : expression->parameters)
            resolve(param.get(), findCandidateFunctions, nullptr);
    }

    TypeDef* resolve(
            Expression* expression,
            function<Function*(function<bool(Function*)>const&)> const & findCandidateFunctions,
            TypeDef* receiverIfKnown) {

        switch (expression->kind) {
            case Expression::INTEGER: return resolveInteger(expression, receiverIfKnown);
            case Expression::STRING: return nullptr;
            case Expression::FLOAT: return nullptr;
            case Expression::NAME: return nullptr;
            case Expression::DOT: return nullptr;
            case Expression::CALL: return resolveCall(expression, findCandidateFunctions, receiverIfKnown);
            default: return nullptr;
        }
    }

    TypeDef* resolve(TypeRef& typeRef, span<ScopeContext> scope) {
        auto& name = typeRef.typeName;
        auto findType = [&](Module* module) -> TypeDef* {
            auto found = find_if(begin(module->types), end(module->types), [&name](auto &t) { return t->name == name; });
            if (found != end(module->types)) {
                typeRef.moduleName = module->name;
                return found->get();
            } else return nullptr;
        };

        if (empty(typeRef.moduleName)) {
            for (auto& sc : scope)
                if (auto typeDef = findType(sc.module); typeDef != nullptr)
                    return typeDef;
        } else {
            auto module = ast.findOrCreateModule(typeRef.moduleName);
            if (auto typeDef = findType(module); typeDef != nullptr)
                return typeDef;
        }
        return nullptr;
    }

    TypeDef* resolve(Function* function, span<ScopeContext> scope) {
        if (function->type == nullptr && !empty(function->result.typeName))
            function->type = resolve(function->result, scope);
        for (auto& parameter : function->parameters)
            resolve(parameter.get(), scope);
        if (function->body)
            resolve(function->body.get(), [](auto a){return nullptr; }, function->type);

        return function->type;
    }

    void resolve(span<ScopeContext> scope) {
        for (auto& sc : scope)
            if (sc.module == nullptr)
                sc.module = ast.findOrCreateModule(sc.moduleName);
    }

    void resolve(Module* module) {
        for (auto& s : module->scopes)
            resolve(s);
        for (auto& f : module->functions)
            resolve(f.get(), f->scope);
    }
};

void findAllTheThings(ast::Ast& ast) {
    TypeResolver resolver(ast, ast.errors);

    for (auto& module : ast.modules)
        resolver.resolve(module.get());
}

