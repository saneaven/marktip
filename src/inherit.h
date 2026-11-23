#pragma once

#include <string>
#include <utility>
#include <vector>

#include "ast.h"

namespace marktip {

// Original JSON keys, including keys whose null or default values were not stored in the AST.
using AttrKeys = std::vector<std::string>;

struct NodeAttrKeys {
    AttrKeys node;
    std::vector<std::pair<std::string, AttrKeys>> marks;
};

using InputAttrKeys = std::vector<NodeAttrKeys>;

void inherit_attrs_and_spelling(Document& document, const Document& base, const InputAttrKeys& present);

}  // namespace marktip
