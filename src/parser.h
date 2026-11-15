#pragma once

#include <string>

#include "ast.h"

namespace marktip {

Document parse_to_document(std::string markdown, bool cjk_friendly, bool html,
                           std::shared_ptr<const Schema> schema);

}  // namespace marktip
