#pragma once

#include "ast.h"

#include <string>

namespace marktip {

std::string to_markdown(const Document& document, bool canonical = false);
std::string render_textblock_for_readback(const Document& document, std::size_t index,
                                          const Node& parent, bool pipe_cell, bool task_checkbox);
std::optional<StoredSpelling> dump_spelling(const Document& document);

}  // namespace marktip
