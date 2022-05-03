//
// Created by Michael Brown on 27/03/2022.
//

#include <functional>

#include "TypeResolver.h"
#include "Tools.h"

using namespace ast;
using namespace std;

struct TypeResolver {
    Ast& ast;
    uint64_t changeCount = 0;
    vector<std::string>& errors;
    
    typedef function<bool(Declaration*)> DeclMatch;
    typedef function<vector<Declaration*>(DeclMatch const &)> DeclResolve;
    
    typedef function<bool(Variable*)> VarMatch;
    typedef function<vector<Variable*>(VarMatch const &)> VarResolve;


    void error(Source const & source, string msg) {
        errors.push_back(source.file + ':' + to_string(source.line) + ',' + to_string(source.character) + ' ' + msg);
    }

    void error(string msg) {
        errors.push_back(msg);
    }


    TypeResolver(Ast& ast, vector<std::string>& errors) : ast(ast), errors(errors) { }



    void resolve(Expression& expression, LoadField& op, DeclResolve const* declResolve, VarResolve const* varResolve, Type const & receiverType) {

    }

    void resolve(Expression& expression, LoadVariable& op, DeclResolve const* declResolve, VarResolve const* varResolve, Type const & receiverType) {
        if (op.variable == nullptr) {
            VarMatch match = [&](auto var){ return var->name == op.fieldName; };
            if (auto fun = receiverType.asFunction()) {
                match = [&](auto var){
                    auto varFun = var->type.asFunction();
                    return varFun && var->name == op.fieldName && varFun->parameter == fun->parameter;
                };
            }

            auto candidates = std::invoke(*varResolve, match);

            if (size(candidates) == 1) {
                op.variable = candidates.front();
                changeCount++;
            } else if (size(candidates) > 1) {
                error("ambiguous reference to variable " + op.fieldName);
            } else {
                error("failed to find variable " + op.fieldName);
            }
        }

        if (!expression.type && op.variable != nullptr && op.variable->type) {
            expression.type = op.variable->type;
            changeCount++;
        }
    }

    void resolve(Expression& expression, StoreField& op, DeclResolve const* declResolve, VarResolve const* varResolve, Type const & receiverType) {

    }

    void resolve(Expression& expression, StoreVariable& op, DeclResolve const* declResolve, VarResolve const* varResolve, Type const & receiverType) {

    }

    void resolve(Expression& expression, Call& op, DeclResolve const* declResolve, VarResolve const* varResolve, Type const & receiverType) {
        // Resolve parameters to get an idea of the function signature
        Function functionSignature { .result = { Type{} } };
        for (auto& param : op.parameters) {
            resolve(param, declResolve, varResolve, {}); // Resolve based on no known receiverType
            functionSignature.parameter.parameters.emplace_back(Parameter{"param", param.type});
        }

        // Try to find the function using what we have learned about the signature
        resolve(op.base.front(), declResolve, varResolve, Type{.type = move(functionSignature)});
    }

    void resolve(Expression& expression, Lambda& op, DeclResolve const* declResolve, VarResolve const* varResolve, Type const & receiverType) {
        for (auto& param : op.parameters)
            resolve(param.type, declResolve, varResolve);

        VarResolve varResolve2 = [&](VarMatch const & match) -> vector<Variable*> {
            vector<Variable*> candidates = std::invoke(*varResolve, match);
            for (auto& parameter : op.parameters)
                if (match(&parameter))
                    candidates.push_back(&parameter);
            return candidates;
        };

        resolve(op.body.front(), declResolve, &varResolve2, receiverType);
    }

    void resolve(Expression& expression, DeclResolve const* declResolve, VarResolve const* varResolve, Type const & receiverType) {
        VarResolve varResolve2 = [&](VarMatch const & match) -> vector<Variable*> {
            vector<Variable*> candidates = std::invoke(*varResolve, match);
            for (auto& variable : expression.variables)
                if (match(&variable))
                    candidates.push_back(&variable);
            return candidates;
        };

        std::visit(overloaded{
            [&](monostate      e) { },
            [&](int64_t        e) { },
            [&](double         e) { },
            [&](string       & e) { },
            [&](LoadField    & e) { resolve(expression, e, declResolve, &varResolve2, receiverType); },
            [&](LoadVariable & e) { resolve(expression, e, declResolve, &varResolve2, receiverType); },
            [&](StoreField   & e) { resolve(expression, e, declResolve, &varResolve2, receiverType); },
            [&](StoreVariable& e) { resolve(expression, e, declResolve, &varResolve2, receiverType); },
            [&](Call         & e) { resolve(expression, e, declResolve, &varResolve2, receiverType); },
            [&](Lambda       & e) { resolve(expression, e, declResolve, &varResolve2, receiverType); },
            [&](Intrinsic    & e) { }
        }, expression.op);
    }

    void resolve(Tuple& tuple, DeclResolve const* declResolve, VarResolve const* varResolve) {
        for (auto& param : tuple.parameters)
            resolve(param.type, declResolve, varResolve);
    }

    void resolve(Function& function, DeclResolve const* declResolve, VarResolve const* varResolve) {
        resolve(function.parameter, declResolve, varResolve);
        resolve(function.result.front(), declResolve, varResolve);
    }

    void resolve(Named& named, DeclResolve const* declResolve, VarResolve const* varResolve) {
        if (named.declaration == nullptr) {
            vector<Declaration*> candidates;

            if (named.module == nullptr) {
                DeclMatch match = [&](Declaration const * declaration){return declaration->name == named.typeName;};
                candidates = std::invoke(*declResolve, match);
            } else {
                for (auto &declaration: named.module->declarations)
                    if (declaration.name == named.typeName)
                        candidates.emplace_back(&declaration);
            }

            if (size(candidates) == 1) {
                named.declaration = candidates.front();
                named.module = named.declaration->scope->owner;
                changeCount++;
            } else if (size(candidates) > 1) {
                error("named type " + named.typeName + " has multiple definitions in module path");
            } else {
                error("named type " + named.typeName + " not found in module path");
            }
        }
    }

    void resolve(Type& type, DeclResolve const* declResolve, VarResolve const* varResolve) {
        std::visit(overloaded{
            [&](Tuple   & t) { resolve(t, declResolve, varResolve); },
            [&](Function& t) { resolve(t, declResolve, varResolve); },
            [&](Named   & t) { resolve(t, declResolve, varResolve); },
            [ ](monostate  ) { }
        }, type.type);
    }

    void resolve(Variable& variable, DeclResolve const* declResolve, VarResolve const* varResolve) {
        pair<DeclResolve, VarResolve> resolver;
        if (variable.scope) {
            resolver = ScopeResolver(variable.scope);
            declResolve = &resolver.first;
            varResolve = &resolver.second;
        }

        resolve(variable.type, declResolve, varResolve);
        resolve(variable.value, declResolve, varResolve, variable.type);
        if (!variable.type && variable.value.type) {
            variable.type = variable.value.type;
            changeCount++;
        }
    }

    void resolve(Structure& structure, DeclResolve const* declResolve, VarResolve const* varResolve) {
        for (auto& field : structure.fields)
            resolve(field.type, declResolve, varResolve);
    }

    void resolve(Primitive& primitive, DeclResolve const* declResolve, VarResolve const* varResolve) {
        // NOP
    }

    void resolve(Declaration& declaration, DeclResolve const* declResolve, VarResolve const* varResolve) {
        pair<DeclResolve, VarResolve> resolver;
        if (declaration.scope) {
            resolver = ScopeResolver(declaration.scope);
            declResolve = &resolver.first;
            varResolve = &resolver.second;
        }
        
        visit(overloaded{
            [&](Structure& t){resolve(t, declResolve, varResolve); },
            [&](Primitive& t){resolve(t, declResolve, varResolve); }
        }, declaration.type);
    }

    pair<DeclResolve, VarResolve> ScopeResolver(ScopeContext const * scope) {
        return pair{
            DeclResolve{[scope](DeclMatch const & match) -> vector<Declaration*> {
                vector<Declaration*> candidates;
                for (auto modulePtr : scope->modules)
                    for (auto& declaration : modulePtr->declarations)
                        if (match(&declaration))
                            candidates.push_back(&declaration);
                return candidates;
            }},
            VarResolve{[scope](VarMatch const & match) -> vector<Variable*> {
                vector<Variable*> candidates;
                for (auto modulePtr : scope->modules)
                    for (auto& variable : modulePtr->variables)
                        if (match(&variable))
                            candidates.push_back(&variable);
                return candidates;
            }}
        };
    }

    void resolve(Module& module) {
        auto [declResolve, varResolve] = ScopeResolver(module.selfScope);

        for (auto& declaration : module.declarations)
            resolve(declaration, &declResolve, &varResolve);
        for (auto& variable : module.variables)
            resolve(variable, &declResolve, &varResolve);
    }
};

void findAllTheThings(ast::Ast& ast) {
    TypeResolver resolver(ast, ast.errors);
    uint64_t lastChangeCount;

    do {
        resolver.errors.clear();
        lastChangeCount = resolver.changeCount;
        for (auto& module : ast.modules)
            resolver.resolve(module);
    } while (resolver.changeCount > lastChangeCount);
}

