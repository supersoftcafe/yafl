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
#include <unordered_map>


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
        string name;

        TypeDef(KIND kind, string&& name, string&& irType) : kind(kind), name(std::move(name)), irType(std::move(irType)) { }
        explicit TypeDef(KIND kind) : kind(kind) { }
        virtual ~TypeDef();
    };

    struct BuiltinType : public TypeDef {
        enum TYPE {
            BOOL, INT8, INT16, INT32, INT64, FLOAT32, FLOAT64
        } type;

        BuiltinType(TYPE type, string&& name, string&& irType) : TypeDef(BUILTIN, std::move(name), std::move(irType)), type(type) { }
        ~BuiltinType() override;
    };


    enum class FunctionKind {
        EXPRESSION, ADD, SUB, MUL, DIV, REM,
    };

    struct Function {
        Function() = default;
        Function(string&& name, TypeDef* type) : name{name}, type{type} { }
        Function(FunctionKind kind, string&& name, TypeDef* type, vector<unique_ptr<Function>>&& parameters)
            : kind{kind}, name{std::move(name)}, parameters{std::move(parameters)}, type{type} { }
        ~Function();

        FunctionKind kind = FunctionKind::EXPRESSION;

        string name;
        TypeRef result;
        unique_ptr<Expression> body;
        vector<unique_ptr<Function>> parameters;
        TypeDef* type { nullptr };
    };

    struct Expression {
        Expression() = default;
        virtual ~Expression();

        virtual void accept(Visitor&) = 0;

        TypeDef* type { nullptr };
    };

    struct Declaration : public Expression {
        unordered_multimap<string, unique_ptr<Function>> declarations;
        unique_ptr<Expression> expression;

        Declaration() = default;
        ~Declaration() override;

        void accept(Visitor&) override;
    };

    struct LiteralValue : public Expression {
        string value;
        enum KIND {
            NUMBER,
            NAME,
            STRING
        } kind = NUMBER;

        LiteralValue() = default;
        LiteralValue(KIND kind, string value) : value{value}, kind{kind} { }
        ~LiteralValue() override;

        void accept(Visitor&) override;
    };

    struct DotOperator : public Expression {
        enum KIND {
            DOT = Token::DOT,
        } kind = DOT;
        unique_ptr<Expression> left;
        string right;

        DotOperator() = default;
        ~DotOperator() override;

        void accept(Visitor&) override;
    };

    struct Call : public Expression {
        Call() = default;
        ~Call() override;

        unique_ptr<Expression> function;
        vector<unique_ptr<Expression>> parameters;
        unordered_map<string, unique_ptr<Expression>> namedParameters;

        void accept(Visitor&) override;
    };
//
//    struct BinaryMath : public Expression {
//        enum KIND {
//            ADD = Token::ADD, SUB = Token::SUB, MUL = Token::MUL, DIV = Token::DIV, REM = Token::REM,
//            SHL = Token::SHL,ASHR =Token::ASHR,LSHR = Token::LSHR,
//            AND = Token::AND, XOR = Token::XOR, OR  = Token::OR,
//            EQ  = Token::EQ , NEQ = Token::NEQ, LT  = Token::LT,  LTE = Token::LTE, GT  = Token::GT , GTE = Token::GTE,
//        } kind = ADD;
//        unique_ptr<Expression> left, right;
//
//        BinaryMath() = default;
//        ~BinaryMath() override;
//
//        void accept(Visitor&) override;
//    };
//
//    struct UnaryMath : public Expression {
//        enum KIND {
//            ADD = Token::ADD, SUB = Token::SUB, NOT = Token::NOT,
//        } kind = ADD;
//
//        unique_ptr<Expression> expr;
//
//        UnaryMath() = default;
//        ~UnaryMath() override;
//
//        void accept(Visitor&) override;
//    };


    struct Visitor {
        virtual void visit(LiteralValue*) = 0;
        virtual void visit(Declaration*) = 0;
        virtual void visit(DotOperator*) = 0;
        virtual void visit(Call*) = 0;
//        virtual void visit(BinaryMath*) = 0;
//        virtual void visit(UnaryMath*) = 0;
    };




    // Imports and options that come after a module line in a given file
    // that are used as scope for each of the declarations.
    struct ScopeContext {
        vector<Module*> imports;
    };

    struct Module {
        string name;    // Root has empty string as name
        vector<unique_ptr<Module>>   modules;
        vector<unique_ptr<TypeDef>>  types;
        vector<unique_ptr<Function>> functions;

        explicit Module(string name) : name(std::move(name)) { }

        void addFunction(unique_ptr<Function>&&);
    };

    struct Ast {
        unique_ptr<Module> root;

        Ast();
        ~Ast();

        Module* findOrCreateModule(char const * name1);
        Module* findOrCreateModule(char const * name1, char const * name2);
        Module* findOrCreateModule(vector<string> const & path);
    };
};

#endif //YAFLCC_AST_H
