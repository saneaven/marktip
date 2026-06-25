#pragma once

#include "ast.h"

#include <pybind11/pybind11.h>

namespace marktip {

Document from_markdown_py(pybind11::object markdown);

}  // namespace marktip
