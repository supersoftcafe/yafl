//
// Created by Michael Brown on 01/04/2022.
//

#ifndef YAFLCC_VERIFIER_H
#define YAFLCC_VERIFIER_H

#include "Ast.h"

class Verifier : private ast::Visitor {
private:
    ast::Ast& ast;

    void error(std::string);
    void verifyType(ast::TypeDef*);
    void verifyModule(ast::Module*);
    void verifyFunction(ast::Function*);
    void verifyExpression(ast::Expression*);

    void visit(ast::LiteralValue*) override;
    void visit(ast::Declaration*) override;
    void visit(ast::DotOperator*) override;
    void visit(ast::Call*) override;
//    void visit(ast::BinaryMath*) override;
//    void visit(ast::UnaryMath*) override;

public:
    std::vector<std::string> errors;

    explicit Verifier(ast::Ast&);
    ~Verifier() = default;


};


#endif //YAFLCC_VERIFIER_H
