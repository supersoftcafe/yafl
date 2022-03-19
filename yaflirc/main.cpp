
#include "parser.h"
#include <fstream>

int main(int argc, char** argv) {
    std::ifstream in { argv[1] };
    convert_yaflir_to_llvmir(in, std::cout);
    return 0;
}