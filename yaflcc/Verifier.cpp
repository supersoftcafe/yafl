//
// Created by Michael Brown on 01/04/2022.
//

#include "Verifier.h"


Verifier::Verifier(ast::Ast& ast) : ast(ast) {
    if (ast.root)
        verifyModule(ast.root.get());
}

void Verifier::error(std::string msg) {
    errors.emplace_back(std::move(msg));
}

void Verifier::verifyModule(ast::Module * module) {
    for (auto& typ : module->types)
        verifyType(typ.second.get());
    for (auto& fun : module->functions)
        verifyFunction(fun.second.get());
    for (auto& mod : module->modules)
        verifyModule(mod.second.get());
}

void Verifier::verifyFunction(ast::Function * function) {
    if (!function->body)
         error("Function " + function->name + " has no implementation");
    else verifyExpression(function->body.get());

    if (!function->type)
        error("Function " + function->name + " has no type");

    for (auto& param : function->params)
        verifyFunction(param.get());
}

void Verifier::verifyType(ast::TypeDef * type) {

}

void Verifier::verifyExpression(ast::Expression * expression) {
    if (!expression->type)
        error("Expression has no type");
    expression->accept(*this);
}


void Verifier::visit(ast::LiteralValue* expression) {

}

void Verifier::visit(ast::Declaration* expression) {

}

void Verifier::visit(ast::DotOperator* expression) {

}

void Verifier::visit(ast::Call* expression) {

}

//void Verifier::visit(ast::BinaryMath* expression) {
////    if (expression->left->type != expression->right->type)
//}
//
//void Verifier::visit(ast::UnaryMath* expression) {
//
//}
