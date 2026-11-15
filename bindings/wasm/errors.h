#pragma once

#include <stdexcept>

namespace marktip::wasm {

class TypeError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

}  // namespace marktip::wasm
