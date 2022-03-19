//
// Created by Michael Brown on 15/03/2022.
//

#ifndef YAFLIRC_INPUT_H
#define YAFLIRC_INPUT_H

#include <sstream>
#include <vector>

class input {
private:
    std::istringstream in { "" };
    std::vector<std::string> tokens_vector { };
    int tokennumber = 0;

public:
    std::string line;
    int linenumber = 0;

    void reset(std::string const & data, int firstLine);

    bool getline();
    std::string pop();
    std::string peek();

    [[noreturn]]
    void rfatal(int line, char const * file, std::string_view msg) const;
    void rwarn(int line, char const * file, std::string_view msg) const;

#define fatal(msg)  in.rfatal(__LINE__, __FILE__, msg)
#define warn(msg)   in.rwarn(__LINE__, __FILE__, msg)
};


#endif //YAFLIRC_INPUT_H
