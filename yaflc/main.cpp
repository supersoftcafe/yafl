
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

#include "tokenizer.h"
#include "parser.h"

using namespace std;





string read_file(const filesystem::path& filename) {
    ifstream stream { filename };
    return {istreambuf_iterator<char>(stream), istreambuf_iterator<char>()};
}

void print_errors(list<ps::Node>::iterator head, list<ps::Node>::iterator tail) {
    for (; head != tail; ++head) {
        if (!std::empty(head->error)) {
            cout << "line " << head->line.line << " column " << head->line.offset << endl
                 << head->error << endl
                 << endl;
        }
    }
}

int main() {
    auto path = filesystem::current_path();

    cout << path << endl;

    auto text = read_file("../examples/test.yafl");
    auto tokens = tk::tokenize(text);
    auto nodes = ps::parse(tokens);
    print_errors(begin(nodes), end(nodes));

    return 0;
}
