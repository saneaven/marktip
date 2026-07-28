#pragma once

#include "ast.h"

#include <pybind11/pybind11.h>

namespace marktip {

Document from_markdown_py(pybind11::object markdown, bool cjk_friendly, bool html, pybind11::object link_schemes,
                          pybind11::object image_schemes, pybind11::object link_relative,
                          pybind11::object image_relative);

}  // namespace marktip
