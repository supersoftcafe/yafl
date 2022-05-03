//
// Created by Michael Brown on 03/05/2022.
//

#ifndef YAFLCC_TYPE_H
#define YAFLCC_TYPE_H

#include <variant>
#include <vector>
#include <string>

#include "Tools.h"

namespace ast {
    using namespace std;


    struct Module;
    struct Declaration;
    struct Parameter;
    struct Type;


    struct Named {
        string typeName;
        Module* module;
        Declaration* declaration;

        ~Named();
        bool operator == (Named const & b) const;
    };

    struct Tuple {
        vector<Parameter> parameters;

        ~Tuple();
        bool operator == (Tuple const & b) const;
    };

    struct Function {
        Tuple parameter;
        vector<Type> result; /* must be exactly one */

        ~Function();
        bool operator == (Function const & b) const;
    };

    struct Type {
        variant<monostate, Named, Tuple, Function> type;

        ~Type();
        bool operator == (Type const &) const;
        operator bool () { return !holds_alternative<monostate>(type); }

        Named* asNamed() { return get_if<Named>(&type); }
        Function* asFunction() { return get_if<Function>(&type); }
        Tuple* asTuple() { return get_if<Tuple>(&type); }

        Named const* asNamed() const { return get_if<Named>(&type); }
        Function const* asFunction() const { return get_if<Function>(&type); }
        Tuple const* asTuple() const { return get_if<Tuple>(&type); }
    };

    struct Parameter {
        string name;
        Type   type;

        ~Parameter();
        bool operator == (Parameter const & b) const;
    };

};


#endif //YAFLCC_TYPE_H
