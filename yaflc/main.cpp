
#include <cstdint>
#include <vector>
#include <iostream>
#include <string_view>
#include <fstream>
#include <format>
#include <regex>
#include <filesystem>
#include <string>
#include <streambuf>
#include <optional>
#include <tuple>
#include <span>

#include "parse2.h"

using namespace std;




/*
string read_file(const filesystem::path& filename) {
    ifstream stream { filename };
    return {istreambuf_iterator<char>(stream), istreambuf_iterator<char>()};
}

void print_errors(list<Error>& errors) {
    for (auto& e : errors) {
        cout << "line " << e.line.line << " column " << e.line.offset << endl
                << e.message << endl
                << endl;
    }
}*/

int main() {
    yafl::run_tests();
/*
    auto path = filesystem::current_path();
    cout << path << endl;

    auto text = read_file("../examples/test.yafl");
    auto tokens = tk::tokenize(text);
    auto [nodes, errors] = ps::parse(tokens);
    print_errors(errors);*/

    return 0;
}
