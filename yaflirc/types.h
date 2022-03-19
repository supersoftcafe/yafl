//
// Created by Michael Brown on 12/03/2022.
//

#ifndef YAFLIRC_TYPES_H
#define YAFLIRC_TYPES_H

#include <vector>
#include <string>
#include <sstream>

namespace ir {

    struct Type {
        std::string name;
        std::vector<Type> members;
        size_t size, align, count;
        enum { Void, Bool, DataPointer, MethodPointer, AtomicCounter, Size, Int, Float, Union, Struct, Array } kind;
    };

    bool parse_typestr(std::string const &typestr, size_t wordSize, Type &type);

    std::string type_to_llvm_name(ir::Type const & type);
};

#endif //YAFLIRC_TYPES_H
