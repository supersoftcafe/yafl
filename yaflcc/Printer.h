//
// Created by Michael Brown on 29/04/2022.
//

#ifndef YAFLCC_PRINTER_H
#define YAFLCC_PRINTER_H

#include <ostream>
#include <string>
#include <set>
#include "Ast.h"
#include "Tools.h"



std::ostream& operator << (std::ostream& out, ast::Intrinsic const& e);

std::ostream& operator << (std::ostream& out, ast::Condition const& e);

std::ostream& operator << (std::ostream& out, ast::Call const& e);

std::ostream& operator << (std::ostream& out, ast::StoreVariable const& e);

std::ostream& operator << (std::ostream& out, ast::StoreField const& e);

std::ostream& operator << (std::ostream& out, ast::LoadVariable const& e);

std::ostream& operator << (std::ostream& out, ast::LoadField const& e);

std::ostream& operator << (std::ostream& out, ast::Expression const& expr);

std::ostream& operator << (std::ostream& out, ast::Tuple const& type);

std::ostream& operator << (std::ostream& out, ast::Function const& type);

std::ostream& operator << (std::ostream& out, ast::Named const& type);

std::ostream& operator << (std::ostream& out, ast::Type const& type);

std::ostream& operator << (std::ostream& out, ast::Variable const& variable);

std::ostream& operator << (std::ostream& out, ast::Module const& module);

std::ostream& operator << (std::ostream& out, ast::Ast const& ast);



#endif //YAFLCC_PRINTER_H
