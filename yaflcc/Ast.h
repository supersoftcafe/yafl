//
// Created by Michael Brown on 18/03/2022.
//

#ifndef YAFLCC_AST_H
#define YAFLCC_AST_H


#include <memory>
#include <variant>
#include <string>
#include <vector>
#include <map>


namespace ast {
    struct Type {
        std::string name;
    };

    struct TypeDeclaration {
        std::vector<std::string> qualifiedName;
    };

    struct Visitor;
    struct Expression {
        Expression() = default;
        virtual ~Expression();

        virtual void visit(Visitor&) = 0;
        virtual std::shared_ptr<Expression> copy() = 0;
    };

    struct Value : public Expression {
        Value() = default;
        ~Value() override;

        void visit(Visitor&) override;
        std::shared_ptr<Expression> copy() override;
        static std::shared_ptr<Value> create();

        std::string value;
    };

    struct Declaration : public Expression {
        Declaration() = default;
        ~Declaration() override;

        void visit(Visitor&) override;
        std::shared_ptr<Expression> copy() override;
        static std::shared_ptr<Declaration> create();

        std::string name;
        std::shared_ptr<Type> type;
        std::shared_ptr<Expression> init, next;
    };

    struct Binary : public Expression {
        Binary() = default;
        ~Binary() override;

        void visit(Visitor&) override;
        std::shared_ptr<Expression> copy() override;
        static std::shared_ptr<Binary> create();

        enum KIND { ADD, SUB, MUL, DIV, REM } kind = ADD;
        std::shared_ptr<Expression> left, right;
    };

    struct Bitwise : public Expression {
        Bitwise() = default;
        ~Bitwise() override;

        void visit(Visitor&) override;
        std::shared_ptr<Expression> copy() override;
        static std::shared_ptr<Bitwise> create();

        enum KIND { ROR, ROL, AND, XOR, OR } kind = ROR;
        std::shared_ptr<Expression> left, right;
    };


    struct Visitor {
        virtual void onValue(Value*) = 0;
        virtual void onDeclaration(Declaration*) = 0;
        virtual void onBinary(Binary*) = 0;
        virtual void onBitwise(Bitwise*) = 0;
    };


    struct Function {
        std::string name;
        std::shared_ptr<Type> result;
        std::vector<std::pair<std::string, std::shared_ptr<Type>>> params;
        std::shared_ptr<Expression> body;
    };


    struct Ast {
        std::string name;
        std::map<std::string, std::shared_ptr<Type>>     types;
        std::map<std::string, std::shared_ptr<Function>> functions;
    };
};

#endif //YAFLCC_AST_H
