//
// Created by Michael Brown on 01/04/2022.
//

#include "Verifier.h"

using namespace std;
using namespace ast;

struct Verifier {
    Ast& ast;
    vector<string>& errors;

    Verifier(Ast& ast, vector<string>& errors) : ast(ast), errors(errors) { }

    void error(string msg) {
        errors.emplace_back(move(msg));
    }

    void verifyType(TypeDef* type) {

    }

    void verifyModule(Module* module) {
        for (auto& typ : module->types)
            verifyType(typ.get());
        for (auto& fun : module->functions)
            verifyFunction(fun.get());
    }

    void verifyFunction(Function* function) {
        if (function->body)
            verifyExpression(function->body.get());

        if (!function->type)
            error("Function " + function->name + " has no type");

        for (auto& param : function->parameters)
            verifyFunction(param.get());
    }

    void verifyExpression(Expression* expression) {
        if (!expression->type)
            error("Expression has no type");

        for (auto& declaration : expression->declarations)
            verifyFunction(declaration.get());
        for (auto& parameter : expression->parameters)
            verifyExpression(parameter.get());

        switch (expression->kind) {
            case Expression::INTEGER:
            case Expression::STRING:
            case Expression::FLOAT:
            case Expression::NAME:
                break;
            case Expression::DOT:
                break;
            case Expression::CALL:
                break;
        }
    }
};




void verifyAllTheThings(Ast& ast) {
    Verifier verifier(ast, ast.errors);

    for (auto& module : ast.modules)
        if (module->name != "System")
            verifier.verifyModule(module.get());
}
