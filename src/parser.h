#pragma once

#include <string>

#include "ast.h"

namespace marktip {

struct ParseOptions {
    bool cjk_friendly = false;
    bool html = true;
    bool partial = false;
    bool keep_source = true;
};

Document parse_to_document(std::string markdown, const ParseOptions& options,
                           std::shared_ptr<const Schema> schema);

}  // namespace marktip
