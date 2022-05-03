//
// Created by Michael Brown on 03/05/2022.
//

#include "Type.h"

namespace ast {

    Named::~Named() = default;
    bool Named::operator == (Named const & b) const {
        return typeName == b.typeName && declaration == b.declaration;
    }

    Tuple::~Tuple() = default;
    bool Tuple::operator == (Tuple const & b) const {
        return parameters == b.parameters;
    }

    Function::~Function() = default;
    bool Function::operator == (Function const & b) const {
        return parameter == b.parameter && result == b.result;
    }

    Type::~Type() = default;
    bool Type::operator == (Type const & b) const {
        return type == b.type;
    }

    Parameter::~Parameter() = default;
    bool Parameter::operator == (Parameter const & b) const {
        return type == b.type;
    }
};