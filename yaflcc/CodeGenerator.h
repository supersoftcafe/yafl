//
// Created by Michael Brown on 27/03/2022.
//

#ifndef YAFLCC_CODEGENERATOR_H
#define YAFLCC_CODEGENERATOR_H

#include <ostream>

#include "Ast.h"


void generateTheCode(ast::Ast&, std::ostream&);


#endif //YAFLCC_CODEGENERATOR_H
