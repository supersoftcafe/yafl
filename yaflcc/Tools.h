//
// Created by Michael Brown on 13/04/2022.
//

#ifndef YAFLCC_TOOLS_H
#define YAFLCC_TOOLS_H

#include <vector>

template<class... Ts> struct overloaded : Ts... { using Ts::operator()...; };
template<class... Ts> overloaded(Ts...) -> overloaded<Ts...>;

template <class T>
std::vector<T> operator + (std::vector<T> const & a, std::vector<T> const & b) {
    std::vector<T> result;
    std::copy(std::cbegin(a), std::cend(a), std::back_inserter(result));
    std::copy(std::cbegin(b), std::cend(b), std::back_inserter(result));
    return std::move(result);
}

template <class T>
std::vector<T> operator + (std::vector<T> const & a, T const & b) {
    std::vector<T> result;
    std::copy(std::cbegin(a), std::cend(a), std::back_inserter(result));
    result.push_back(b);
    return std::move(result);
}

template <class T>
std::vector<T>& operator += (std::vector<T> & result, std::vector<T> const & a) {
    std::copy(std::cbegin(a), std::cend(a), std::back_inserter(result));
    return result;
}

template <class T>
std::vector<T>& operator += (std::vector<T> & result, T a) {
    result.emplace_back(std::move(a));
    return result;
}

//template <class T>
//bool operator == (std::span<T> const & a, std::span<T> const & b) {
//    if (std::size(a) == std::size(b)) {
//        for (ssize_t index = std::size(a); --index >= 0; )
//            if (a[index] != b[index])
//                return false;
//        return true;
//    }
//    return false;
//}

#endif //YAFLCC_TOOLS_H
