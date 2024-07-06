
#ifndef YAFLC_PARSE2_H
#define YAFLC_PARSE2_H

#include <list>
#include <tuple>
#include <string>
#include <vector>
#include <memory>
#include <ostream>
#include "error.h"
#include "source.h"


namespace yafl {

    using namespace std;



    struct String;
    struct Integer;
    struct BinaryOp;
    struct Lambda;
    struct Expression {
        using ptr = unique_ptr<Expression>;
        using var = variant<String const*,Integer const*,BinaryOp const*,Lambda const*>;
        constexpr virtual ~Expression() { }
        constexpr virtual var as_variant() const = 0;
        constexpr virtual bool is_equal(const Expression*) const = 0;
        virtual void print(ostream&) const = 0;
    };

    constexpr bool is_equal(const Expression::ptr& a, const Expression::ptr& b) {
        return (!a && !b) || (a && b && a->is_equal(b.get()));
    }

    inline ostream& operator << (ostream& o, const Expression::ptr& p) {
        p->print(o);
        return o;
    }



    struct Value;
    struct Alias;
    struct Import;
    struct Namespace;
    struct Declaration {
        using ptr = unique_ptr<Declaration>;
        using var = variant<Value const*,Alias const*,Import const*,Namespace const*>;
        constexpr virtual ~Declaration() { }
        constexpr virtual var as_variant() const = 0;
        constexpr virtual bool is_equal(const Declaration*) const = 0;
        virtual void print(ostream&) const = 0;
    };

    constexpr bool is_equal(const Declaration::ptr& a, const Declaration::ptr& b) {
        return (!a && !b) || (a && b && a->is_equal(b.get()));
    }

    constexpr bool is_equal(const vector<Declaration::ptr>& a, const vector<Declaration::ptr>& b) {
        if (std::size(a) != std::size(b)) return false;
        for (size_t index = 0; index < std::size(a); ++index)
            if (!is_equal(a[index], b[index]))
                return false;
        return true;
    }

    inline ostream& operator << (ostream& o, const Declaration::ptr& p) {
        p->print(o);
        return o;
    }

    inline ostream& operator << (ostream& o, const vector<Declaration::ptr>& declarations) {
        o << "vector<Declaration::ptr> {";
        for (const auto& p : declarations)
            o << p << ", ";
        o << "}";
        return o;
    }



    struct String : Expression {
        explicit constexpr String(string value) : value(value) { }
        static constexpr Expression::ptr create(string value){return make_unique<String>(value);}
        constexpr var as_variant() const {return this;}
        constexpr bool is_equal(const Expression* o) const {
            auto v = o->as_variant();
            if (String const** pval = std::get_if<String const*>(&v)) {
                return value == (*pval)->value;
            } else {
                return false;
            }
        }
        void print(ostream& o) const {
            o << "String(\"" << value << "\")";
        }
        const string value;
    };

    struct Integer : Expression {
        explicit constexpr Integer(int64_t value, uint_fast8_t size) : value(value), size(size) { }
        static constexpr Expression::ptr create(int64_t value, uint_fast8_t size){return make_unique<Integer>(value, size);}
        constexpr var as_variant() const {return this;}
        constexpr bool is_equal(const Expression* o) const {
            auto v = o->as_variant();
            if (Integer const** pval = std::get_if<Integer const*>(&v)) {
                return value == (*pval)->value && size == (*pval)->size;
            } else {
                return false;
            }
        }
        void print(ostream& o) const {
            o << "Integer(" << value << ", " << int(size) << ")";
        }
        const int64_t value;
        const uint_fast8_t size;
    };

    struct BinaryOp : Expression {
        enum Op : char { MUL='*', DIV='/', REM='%', ADD='+', SUB='-' };
        explicit constexpr BinaryOp(Expression::ptr&&l,char op,Expression::ptr&&r) : left(std::move(l)),right(std::move(r)),op(op) { }
        static constexpr Expression::ptr create(Expression::ptr&&l,char op,Expression::ptr&&r){return make_unique<BinaryOp>(std::move(l),op,std::move(r));}
        constexpr var as_variant() const {return this;}
        constexpr bool is_equal(const Expression* o) const {
            auto v = o->as_variant();
            if (BinaryOp const** pval = std::get_if<BinaryOp const*>(&v)) {
                return op == (*pval)->op && yafl::is_equal(left, (*pval)->left) && yafl::is_equal(right, (*pval)->right);
            } else {
                return false;
            }
        }
        void print(ostream& o) const {
            o << "BinaryOp(" << left << ", \'" << op << "\', " << right << ")";
        }
        const Expression::ptr left;
        const Expression::ptr right;
        const char op;
    };

    struct Lambda : Expression {
        constexpr Lambda(vector<Declaration::ptr>&& declarations) : declarations { std::move(declarations) } { }
        static constexpr Expression::ptr create(vector<Declaration::ptr>&& declarations){return make_unique<Lambda>(std::move(declarations));}
        constexpr var as_variant() const {return this;}
        constexpr bool is_equal(const Expression* o) const {
            auto v = o->as_variant();
            if (Lambda const** pval = std::get_if<Lambda const*>(&v)) {
                return yafl::is_equal(declarations, (*pval)->declarations);
            } else {
                return false;
            }
        }
        void print(ostream& o) const {
            o << "Lambda(" << declarations << ")";
        }
        const vector<Declaration::ptr> declarations;
    };



    struct Value : Declaration {
        constexpr Value(string&& name, Expression::ptr&& value) : name { std::move(name) }, value { std::move(value) } { }
        static constexpr Declaration::ptr create(string&& name, Expression::ptr&& value){return make_unique<Value>(std::move(name), std::move(value));}
        constexpr var as_variant() const {return this;}
        constexpr bool is_equal(const Declaration* o) const {
            auto v = o->as_variant();
            if (Value const** pval = std::get_if<Value const*>(&v)) {
                return name == (*pval)->name && yafl::is_equal(value, (*pval)->value);
            } else {
                return false;
            }
        }
        void print(ostream& o) const {
            o << "Value(\"" << name << "\", " << value << ")";
        }
        const string name;
        const Expression::ptr value;
    };

    struct Alias : Declaration {
        constexpr Alias(string&& name, string&& somesuch) : name { std::move(name) }, somesuch { std::move(somesuch) } { }
        static constexpr Declaration::ptr create(string&& name, string&& somesuch){return make_unique<Alias>(std::move(name), std::move(somesuch));}
        constexpr var as_variant() const {return this;}
        constexpr bool is_equal(const Declaration* o) const {
            auto v = o->as_variant();
            if (Alias const** pval = std::get_if<Alias const*>(&v)) {
                return name == (*pval)->name && somesuch == (*pval)->somesuch;
            } else {
                return false;
            }
        }
        void print(ostream& o) const {
            o << "Alias(\"" << name << "\", \"" << somesuch << "\")";
        }
        const string name;
        const string somesuch;
    };

    struct Import : Declaration {
        constexpr Import(vector<string>&& name) : name { std::move(name) } { }
        static constexpr Declaration::ptr create(vector<string>&& name){return make_unique<Import>(std::move(name));}
        constexpr var as_variant() const {return this;}
        constexpr bool is_equal(const Declaration* o) const {
            auto v = o->as_variant();
            if (Import const** pval = std::get_if<Import const*>(&v)) {
                return name == (*pval)->name;
            } else {
                return false;
            }
        }
        void print(ostream& o) const {
            o << "Import(vector<string>{";
            for (const auto& s : name)
                o << s << ", ";
            o << "})";
        }
        const vector<string> name;
    };

    struct Namespace : Declaration {
        constexpr Namespace(vector<string>&& name) : name { std::move(name) } { }
        static constexpr Declaration::ptr create(vector<string>&& name){return make_unique<Namespace>(std::move(name));}
        constexpr var as_variant() const {return this;}
        constexpr bool is_equal(const Declaration* o) const {
            auto v = o->as_variant();
            if (Namespace const** pval = std::get_if<Namespace const*>(&v)) {
                return name == (*pval)->name;
            } else {
                return false;
            }
        }
        void print(ostream& o) const {
            o << "Import(vector<string>{";
            for (const auto& s : name)
                o << s << ", ";
            o << "})";
        }
        const vector<string> name;
    };



    struct ErrorMessage {
        SourceRef sourceRef;
        string_view message;

        constexpr ErrorMessage(SourceRef sourceRef, string_view message) : sourceRef(sourceRef), message(message) { }
        constexpr ErrorMessage(Source source, string_view message) : sourceRef(source.sourceRef()), message(message) { }

        constexpr auto operator == (const auto& o) const {
            return sourceRef == o.sourceRef && message == o.message;
        }
        constexpr operator bool () const {
            return !empty(message);
        }

        // Delete copy constructor and assignment operator
        ErrorMessage(const ErrorMessage&) = delete;
        ErrorMessage& operator=(const ErrorMessage&) = delete;
        ErrorMessage(ErrorMessage&&) = default;
    };

    void run_tests();

    tuple<vector<Declaration::ptr>, vector<ErrorMessage>> constexpr parse(Source s);
}

#endif

