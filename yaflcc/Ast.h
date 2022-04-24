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
#include <vector>
#include <unordered_set>
#include <span>
#include <ostream>


namespace ast {
    using namespace std;


    struct Module;
    struct Visitor;
    struct Function;
    struct TypeDef;
    struct Expression;




    // Imports and options that come after a module line in a given file
    // that are used as scope for each of the declarations.
    struct ScopeContext {
        string moduleName ;
        Module*    module = nullptr;
    };

    struct TypeRef {
        string moduleName;
        string typeName;
        vector<TypeRef> parameters;
    };

    struct TypeDef {
        enum KIND {
            BUILTIN, STRUCTURE, CLASS, FUNCTION
        } kind = BUILTIN;
        string name;
        string irType;
        span<ScopeContext> scope;
    };

    struct GenericParam {
        string name;
    };

    struct Function {
        string name;
        TypeRef result;
        unordered_set<string> annotations;
        unique_ptr<Expression> body;
        vector<unique_ptr<Function>> parameters;
        vector<GenericParam> genericParameters;
        TypeDef* type { nullptr };
        span<ScopeContext> scope;

        ~Function();
        void print(ostream&);
    };

    struct Expression {
        vector<unique_ptr<Function>> declarations;
        vector<unique_ptr<Expression>> parameters; // For CALL 1st entry is the function, the rest are the params
        TypeDef* type { nullptr };
        string value;
        enum KIND {
            INTEGER, FLOAT, STRING,

            UNQUALIFIED_NAME,
            QUALIFIED_NAME,     // Left hand side could resolve to instance or type
            CALL
        } kind;

        Expression(KIND k, vector<unique_ptr<Expression>> p) : parameters(move(p)), kind(k) { }
        Expression(KIND k, string v) : value(move(v)), kind(k) { }
        ~Expression() = default;

        void print(ostream&);
    };

    struct Module {
        string name;

        vector<vector<ScopeContext>> scopes;
        vector<unique_ptr<TypeDef>>  types;
        vector<unique_ptr<Function>> functions;
    };

    struct Ast {
        vector<string> errors;
        vector<unique_ptr<Module>> modules;

        TypeDef* typeBool  = nullptr;
        TypeDef* typeInt8  = nullptr;
        TypeDef* typeInt16 = nullptr;
        TypeDef* typeInt32 = nullptr;
        TypeDef* typeInt64 = nullptr;
        TypeDef* typeFloat32 = nullptr;
        TypeDef* typeFloat64 = nullptr;

        Ast();
        ~Ast();

        Module* findOrCreateModule(string const & path);
    };
};

inline std::ostream& operator << (std::ostream& out, std::unique_ptr<ast::Expression> const & expr) {
    expr->print(out);
    return out;
}

inline std::ostream& operator << (std::ostream& out, std::unique_ptr<ast::Function> const & function) {
    function->print(out);
    return out;
}

#endif //YAFLCC_AST_H
