//
// Created by Michael Brown on 27/03/2022.
//

#ifndef YAFLCC_TYPERESOLVER_H
#define YAFLCC_TYPERESOLVER_H

#include "Ast.h"
#include <vector>

class TypeResolver {
private:
    ast::Ast& ast;

public:
    std::vector<std::string> errors;

    TypeResolver(ast::Ast&);
    ~TypeResolver();
};


#endif //YAFLCC_TYPERESOLVER_H
