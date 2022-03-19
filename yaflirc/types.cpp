//
// Created by Michael Brown on 12/03/2022.
//

#include "types.h"
#include <sstream>

namespace ir {

    std::pair<Type, bool> parse_stream(std::istream &ss, size_t wordSize) {
        auto parse_size = [&](size_t& size) -> bool {
            ss >> size;
            return !!ss;
        };

        auto parse_types = [&](std::vector<Type> &members) -> bool {
            for (;;) {
                auto [subtype, success] = parse_stream(ss, wordSize);
                if (!success)
                    return false;
                if (subtype.kind == Type::Void) break;
                members.push_back(std::move(subtype));
            }
            return !members.empty();
        };

        char chr = char(ss.get());
        switch (chr) {
            case 'v':
                return { Type { .name = "v", .size = 0, .align = 0, .count = 0, .kind = Type::Void }, true };
            case 'b':
                return { Type { .name = "b", .size = 1, .align = 1, .count = 0, .kind = Type::Bool }, true };
            case 'p':
                return { Type { .name = "p", .size = wordSize, .align = wordSize, .count = 0, .kind = Type::DataPointer }, true };
            case 'm':
                return { Type { .name = "m", .size = wordSize, .align = wordSize, .count = 0, .kind = Type::MethodPointer }, true };
            case 'c':
                return { Type { .name = "c", .size = wordSize, .align = wordSize, .count = 0, .kind = Type::AtomicCounter }, true };
            case 'i': {
                if (ss.peek() == 's')
                    return { Type { .name = "is", .size = wordSize, .align = wordSize, .count = 0, .kind = Type::Size }, true };
                size_t size;
                if (!parse_size(size))
                    return { Type { }, false };
                return { Type { .name = "i" + std::to_string(size), .size = size, .align = std::min(size, wordSize), .count = 0, .kind = Type::Int }, size == 1 || size == 2 || size == 4 || size == 8 };
            }
            case 'f': {
                size_t size;
                if (!parse_size(size))
                    return { Type { }, false };
                return { Type { .name = "f" + std::to_string(size), .size = size, .align = std::min(size, wordSize), .count = 0, .kind = Type::Float }, size == 4 || size == 8 };
            }
            case 'u': {
                auto type = Type { .name = "u", .size = 0, .align = 0, .count = 0, .kind = Type::Union };
                if (!parse_types(type.members))
                    return { Type { }, false };
                for (auto& member : type.members) {
                    type.align = std::max(type.align, member.align);
                    type.size = std::max(type.size, member.size);
                    type.name += member.name;
                }
                if (type.align == 0)
                    return { Type { }, false };
                type.size = (type.size + type.align - 1) / type.align * type.align;
                type.name += "v";
                return { type, true };
            }
            case 's': {
                auto type = Type { .name = "s", .size = 0, .align = 0, .count = 0, .kind = Type::Struct };
                if (!parse_types(type.members))
                    return { Type { }, false };
                for (auto &member: type.members) {
                    type.size = (type.size + member.align - 1) / member.align * member.align + member.size;
                    type.align = std::max(type.align, member.align);
                    type.name += member.name;
                }
                if (type.align == 0)
                    return { Type { }, false };
                type.name += "v";
                return { type, true };
            }
            case 'a': {
                size_t count;
                if (!parse_size(count))
                    return { Type { }, false };
                auto [subtype, success] = parse_stream(ss, wordSize);
                if (!success)
                    return { Type { }, false };
                Type type = { .name = "a" + std::to_string(count) + subtype.name, .size = count * subtype.size, .align = subtype.align, .count = count, .kind = Type::Array };
                type.members.emplace_back(std::move(subtype));
                return { type, true };
            }
            default:
                return { Type { }, false };
        }
    }

    bool parse_typestr(std::string const &typestr, size_t wordSize, Type &type) {
        std::istringstream ss{typestr};
        auto [resultType, success] = parse_stream(ss, wordSize);
        type = resultType;
        return success;
    }

    std::string type_to_llvm_name(ir::Type const & type) {
        switch (type.kind) {
            case ir::Type::Void:
                return "void";
            case ir::Type::Bool:
                return "i1";
            case ir::Type::DataPointer:
            case ir::Type::MethodPointer:
                return "i8*";
            case ir::Type::AtomicCounter:
            case ir::Type::Size:
            case ir::Type::Int:
                return "i" + std::to_string(type.size * 8);
            case ir::Type::Float:
                return type.size == 4 ? "float" : "double";
            case ir::Type::Union:
            case ir::Type::Struct:
            case ir::Type::Array:
                return "%type." + type.name;
            default:
                abort();
        }
    }
};
