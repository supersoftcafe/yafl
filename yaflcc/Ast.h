//
// Created by Michael Brown on 18/03/2022.
//

#ifndef YAFLCC_AST_H
#define YAFLCC_AST_H

#include "Token.h"

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
    struct Expression;


    struct TypeRef {
        vector<string> names;
    };

    struct TypeDef {
        enum KIND {
            BUILTIN, STRUCTURE, CLASS, FUNCTION
        } kind;
        string irType;

        TypeDef(KIND kind, string&& irType) : kind(kind), irType(irType) { }
        explicit TypeDef(KIND kind) : kind(kind) { }
        virtual ~TypeDef();
    };

    struct BuiltinType : public TypeDef {
        enum TYPE {
            BOOL, INT8, INT16, INT32, INT64, FLOAT32, FLOAT64
        } type;

        BuiltinType(TYPE type, string&& irType) : TypeDef(BUILTIN, std::move(irType)), type(type) { }
        ~BuiltinType() override;
    };



    struct Function {
        string name;
        TypeRef result;
        unique_ptr<Expression> body;
        vector<unique_ptr<Function>> params;
        TypeDef* type;
    };

    struct Expression {
        Expression() = default;
        virtual ~Expression();

        virtual void visit(Visitor&) = 0;

        TypeDef* type;
    };

    struct LiteralValue : public Expression {
        string value;
        enum KIND {
            NUMBER,
            NAME,
            STRING
        } kind = NUMBER;

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
        enum KIND {
            DOT = Token::DOT,
            ADD = Token::ADD, SUB = Token::SUB, MUL = Token::MUL, DIV = Token::DIV, REM = Token::REM,
            SHL = Token::SHL,ASHR =Token::ASHR,LSHR = Token::LSHR,
            AND = Token::AND, XOR = Token::XOR, OR  = Token::OR,
            EQ  = Token::EQ , NEQ = Token::NEQ, LT  = Token::LT,  LTE = Token::LTE, GT  = Token::GT , GTE = Token::GTE,
        } kind = DOT;
        unique_ptr<Expression> left, right;

        Binary() = default;
        ~Binary() override;

        void visit(Visitor&) override;
    };

    struct Unary : public Expression {
        enum KIND {
            ADD = Token::ADD, SUB = Token::SUB, NOT = Token::NOT,
        } kind = ADD;

        unique_ptr<Expression> expr;

        Unary() = default;
        ~Unary() override;

        void visit(Visitor&) override;
    };


    struct Visitor {
        virtual void onValue(LiteralValue*) = 0;
        virtual void onDeclaration(Declaration*) = 0;
        virtual void onBinary(Binary*) = 0;
        virtual void onUnary(Unary*) = 0;
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

        Ast();
        ~Ast();

        ast::Module* findOrCreateModule(char const * name1);
        ast::Module* findOrCreateModule(char const * name1, char const * name2);
        ast::Module* findOrCreateModule(vector<string> const & path);
    };
};

#endif //YAFLCC_AST_H
