#pragma once

#include <pybind11/pybind11.h>

#include "ast.h"
#include "policy.h"
#include "validate.h"

namespace marktip {

pybind11::dict to_dict_py(const Document& document);

// Requires the GIL.
// Malformed option values are a caller bug rather than a malformed document,
// so these raise TypeError/ValueError instead of a MarktipError.
UriPolicy uri_policy_from_py(pybind11::object link_schemes, pybind11::object image_schemes,
                             pybind11::object link_relative, pybind11::object image_relative);
NodeTypePolicy node_type_policy_from_py(pybind11::object reject_node_types, const Schema& schema);
StrictMode strict_from_py(pybind11::handle value, const char* arg_name);
std::shared_ptr<const Schema> schema_from_py(pybind11::handle value);

// `strict` is from_dict-only: the parser emits only declared fields, valid
// content relationships and attrs it understands, so there is nothing on
// from_markdown to catch.
Document from_dict_py(pybind11::dict root, pybind11::object link_schemes, pybind11::object image_schemes,
                      pybind11::object link_relative, pybind11::object image_relative,
                      pybind11::object reject_node_types, pybind11::object strict, pybind11::object schema);
Document from_markdown_py(pybind11::object markdown, bool cjk_friendly, bool html, pybind11::object link_schemes,
                          pybind11::object image_schemes, pybind11::object link_relative,
                          pybind11::object image_relative, pybind11::object reject_node_types,
                          pybind11::object schema);

}  // namespace marktip
