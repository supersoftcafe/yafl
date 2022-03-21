
#include "parser.h"
#include <fstream>
#include <filesystem>

int main(int argc, char** argv) {
    std::ifstream in { argv[1] };

    std::cerr << std::filesystem::current_path() << std::endl;

    convert_yaflir_to_llvmir(in, std::cout);
    return 0;
}