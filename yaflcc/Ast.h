//
// Created by Michael Brown on 18/03/2022.
//

#ifndef YAFLCC_AST_H
#define YAFLCC_AST_H


#include <memory>
#include <utility>
#include <variant>
#include <string>
#include <vector>
#include <map>


namespace ast {
    using namespace std;


    struct Module;
    struct Visitor;
    struct Function;


    struct TypeRef {
        vector<string> names;
    };

    struct TypeDef {
        bool internal;
    };

    struct Expression {
        Expression() = default;
        virtual ~Expression();

        virtual void visit(Visitor&) = 0;
    };

    struct LiteralValue : public Expression {
        string value;
        enum KIND { NUMBER, NAME, STRING } kind = NUMBER;

        LiteralValue() = default;
        ~LiteralValue() override;

        void visit(Visitor&) override;
    };

    struct Declaration : public Expression {
        unique_ptr<Function> definition;
        unique_ptr<Expression>     next;

        Declaration() = default;
        ~Declaration() override;

        void visit(Visitor&) override;
    };

    struct Binary : public Expression {
        enum KIND { ADD, SUB, MUL, DIV, REM } kind = ADD;
        shared_ptr<Expression> left, right;

        Binary() = default;
        ~Binary() override;

        void visit(Visitor&) override;
    };

    struct Bitwise : public Expression {
        enum KIND { ROR, ROL, AND, XOR, OR } kind = ROR;
        unique_ptr<Expression> left, right;

        Bitwise() = default;
        ~Bitwise() override;

        void visit(Visitor&) override;
    };


    struct Visitor {
        virtual void onValue(LiteralValue*) = 0;
        virtual void onDeclaration(Declaration*) = 0;
        virtual void onBinary(Binary*) = 0;
        virtual void onBitwise(Bitwise*) = 0;
    };


    struct Function {
        string name;
        TypeRef result;
        unique_ptr<Expression> body;
        vector<unique_ptr<Function>> params;
    };


    // Imports and options that come after a module line in a given file
    // that are used as scope for each of the declarations.
    struct ScopeContext {
        vector<Module*> imports;
    };

    struct Module {
        string name;    // Root has empty string as name
        map<string, unique_ptr<Module>>   modules;
        map<string, unique_ptr<TypeDef>>  types;
        map<string, unique_ptr<Function>> functions;

        explicit Module(string name) : name(std::move(name)) { }
    };

    struct Ast {
        unique_ptr<Module> root;
    };
};

#endif //YAFLCC_AST_H
