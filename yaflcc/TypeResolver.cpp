//
// Created by Michael Brown on 27/03/2022.
//

#include "TypeResolver.h"

TypeResolver::~TypeResolver() = default;


TypeResolver::TypeResolver(ast::Ast &) : ast(ast) {
    // Iterate over all functions to ensure types are well known
}