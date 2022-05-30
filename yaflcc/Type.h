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


    class Type {
    private:
        struct Impl {
            enum Kind {NAMED, TUPLE, FUNCTION} kind;
            explicit Impl(Kind kind) : kind(kind) { }
            virtual ~Impl() = 0;
        };
        unique_ptr<Impl> pointer { };
        explicit Type(Impl* ptr) : pointer(ptr) { }

    public:
        struct Named;
        struct Tuple;
        struct Function;
        struct Unknown { };
        struct Parameter;

        Type() = default;
        ~Type() = default;
        template <typename TFun> auto visit(TFun fun);
        template <typename TFun> auto visit(TFun fun) const;
        bool operator == (Type const& b) const;

        bool isNamed(   ) const { return pointer && pointer->kind == Impl::NAMED   ; }
        bool isTuple(   ) const { return pointer && pointer->kind == Impl::TUPLE   ; }
        bool isFunction() const { return pointer && pointer->kind == Impl::FUNCTION; }
        bool isUnknown( ) const { return !pointer; }

        Named    const* asNamed(   ) const;
        Tuple    const* asTuple(   ) const;
        Function const* asFunction() const;

        Named   * asNamed(   );
        Tuple   * asTuple(   );
        Function* asFunction();
    };

    class Type::Named : Impl {
    private:
        friend class Type;

    public:
        string typeName;
        Module* module{};
        Declaration* declaration{};

        explicit Named(string typeName) : Impl(NAMED), typeName(move(typeName)) { }
        ~Named() override;
        bool operator == (Named const & b) const;
    };

    class Type::Tuple : Impl {
    private:
        friend class Type;

    public:
        vector<Parameter> parameters;

        Tuple() : Impl(TUPLE) { }
        ~Tuple() override;
        bool operator == (Tuple const & b) const;
    };

    class Type::Function : Impl {
    private:
        friend class Type;

    public:
        Tuple   parameter;
        Type    result; /* must be exactly one */

        Function() : Impl(FUNCTION) { }
        ~Function() override;
        bool operator == (Function const & b) const;
    };

    class Type::Parameter {
    private:
        friend class Type::Tuple;

    public:
        string name;
        Type   type;

        Parameter() = default;
        ~Parameter();
        bool operator == (Parameter const & b) const;
    };

    template <typename TFun>
    auto Type::visit(TFun fun) const {
        switch (pointer ? pointer->kind : -1) {
            case Impl::NAMED   : return fun(*dynamic_cast<Named    const*>(pointer.get()));
            case Impl::TUPLE   : return fun(*dynamic_cast<Tuple    const*>(pointer.get()));
            case Impl::FUNCTION: return fun(*dynamic_cast<Function const*>(pointer.get()));
            default: return fun(Unknown{});
        }
    }

    template <typename TFun>
    auto Type::visit(TFun fun) {
        switch (pointer ? pointer->kind : -1) {
            case Impl::NAMED   : return fun(*dynamic_cast<Named   *>(pointer.get()));
            case Impl::TUPLE   : return fun(*dynamic_cast<Tuple   *>(pointer.get()));
            case Impl::FUNCTION: return fun(*dynamic_cast<Function*>(pointer.get()));
            default: return fun(Unknown{});
        }
    }

    Type::Named    const* Type::asNamed(   ) const { return isNamed(   ) ? dynamic_cast<Named   *>(pointer.get()) : nullptr; }
    Type::Tuple    const* Type::asTuple(   ) const { return isTuple(   ) ? dynamic_cast<Tuple   *>(pointer.get()) : nullptr; }
    Type::Function const* Type::asFunction() const { return isFunction() ? dynamic_cast<Function*>(pointer.get()) : nullptr; }

    Type::Named   * Type::asNamed(   ) { return isNamed(   ) ? dynamic_cast<Named   *>(pointer.get()) : nullptr; }
    Type::Tuple   * Type::asTuple(   ) { return isTuple(   ) ? dynamic_cast<Tuple   *>(pointer.get()) : nullptr; }
    Type::Function* Type::asFunction() { return isFunction() ? dynamic_cast<Function*>(pointer.get()) : nullptr; }
};


#endif //YAFLCC_TYPE_H
