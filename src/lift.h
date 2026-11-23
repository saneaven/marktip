#pragma once

#include <cstddef>

#include "path.h"

namespace marktip {

class Document;
struct NodeSpec;
struct ParseOptions;

void complete_content(Document& document, std::size_t index, const NodeSpec& spec, PathStack& path);
void lift(Document& document, const ParseOptions& options);

}  // namespace marktip
