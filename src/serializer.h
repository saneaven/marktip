#pragma once

#include "ast.h"

#include <string>

namespace marktip {

std::string to_markdown(const Document& document, bool canonical = false);
std::optional<StoredSpelling> dump_spelling(const Document& document);

}  // namespace marktip
