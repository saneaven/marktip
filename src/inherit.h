#pragma once

#include <string>
#include <vector>

#include "ast.h"

namespace marktip {

// Original JSON keys, including keys whose null or default values were not stored in the AST.
struct NodeAttrKeys {
    std::vector<std::string> node;
    std::vector<std::vector<std::string>> marks;
};

using InputAttrKeys = std::vector<NodeAttrKeys>;

void inherit_spelling(Document& document, const Document& base, const InputAttrKeys& present);

}  // namespace marktip
