//
// Created by Michael Brown on 18/03/2022.
//

#ifndef YAFLCC_AST_H
#define YAFLCC_AST_H

#include "Token.h"

#include <functional>
#include <memory>
#include <utility>
#include <variant>
#include <string>
#include <forward_list>
#include <vector>
#include <unordered_set>
#include <span>
#include <ostream>

#include "Type.h"

namespace ast {
    using namespace std;


    struct Module;
    struct Declaration;
    struct Variable;
    struct Expression;

    // Imports and options that come after a module line in a given file
    // that are used as scope for each of the declarations.
    struct ScopeContext {
        Module* owner;
        forward_list<Module*> modules;
    };

    struct Primitive {
        enum Kind { BOOL, INT8, INT16, INT32, INT64, FLOAT32, FLOAT64 } kind;
        string irType;
    };
    struct Field { string name; Type type; };
    struct Structure { vector<Field> fields;};
    struct Declaration {
        ScopeContext* scope;
        string name;
        variant<Primitive, Structure> type;
    };


    struct LoadField {
        string fieldName;
        forward_list<Expression> base; // Must have exactly one element
    };

    struct LoadVariable {
        string fieldName;
        Variable* variable;
    };

    struct StoreField {
        string fieldName;
        forward_list<Expression> base; // Must have exactly one element
        forward_list<Expression> value; // Must have exactly one element
    };

    struct StoreVariable {
        string fieldName;
        Module* module; // If nullptr, module is either not known, or field is local
        forward_list<Expression> value; // Must have exactly one element
    };

    struct Call {
        forward_list<Expression> base; // Must have exactly one element
        forward_list<Expression> parameters;
    };

    struct Lambda {
        forward_list<Variable> parameters;
        forward_list<Expression> body; // Must have exactly one element
    };

    struct Intrinsic {
    };

    struct Expression {
        Source source;
        Type type;
        forward_list<Variable> variables;
        variant<monostate, int64_t, double, string, LoadField, LoadVariable, StoreField, StoreVariable, Call, Lambda, Intrinsic> op;
    };

    struct Variable {
        Source source;
        ScopeContext* scope;
        string name;
        Type type;
        Expression value;
    };






    struct Module {
        string name;
        ScopeContext* selfScope;
        forward_list<ScopeContext>      scopes;
        forward_list<Declaration> declarations;
        forward_list<Variable>       variables;
    };

    struct Ast {
        vector<string> errors;
        forward_list<Module> modules;

        Type typeBool;
        Type typeInt8;
        Type typeInt16;
        Type typeInt32;
        Type typeInt64;
        Type typeFloat32;
        Type typeFloat64;

        Ast();
        ~Ast();

        Module* findOrCreateModule(string const & path);
    };
};


#endif //YAFLCC_AST_H
