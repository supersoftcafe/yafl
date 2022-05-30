//
// Created by Michael Brown on 03/05/2022.
//

#include "Type.h"

namespace ast {

    bool Type::operator == (Type const& b) const {
        return visit(overloaded{
            [&](Type::Tuple    const& a) { auto ptr = b.asTuple(   ); return ptr && a == *ptr; },
            [&](Type::Function const& a) { auto ptr = b.asFunction(); return ptr && a == *ptr; },
            [&](Type::Unknown  const& a) { return false; }
        });
    }

    Type::Named::~Named() = default;
    bool Type::Named::operator == (Named const & b) const {
        return typeName == b.typeName && declaration == b.declaration;
    }

    Type::Tuple::~Tuple() = default;
    bool Type::Tuple::operator == (Tuple const & b) const {
        return parameters == b.parameters;
    }

    Type::Function::~Function() = default;
    bool Type::Function::operator == (Function const & b) const {
        return parameter == b.parameter && result == b.result;
    }

    Type::Parameter::~Parameter() = default;
    bool Type::Parameter::operator == (Type::Parameter const & b) const {
        return type == b.type;
    }
};