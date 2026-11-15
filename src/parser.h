#pragma once

#include <optional>
#include <string>

#include "ast.h"

namespace marktip {

// Temporary parse observation for the segment proof, before spelling is exposed by dump().
struct ParseSegment {
    std::size_t start;
    std::optional<std::size_t> root_child;
};

struct ParseObservation {
    std::vector<ParseSegment> segments;
    std::size_t root_child_count = 0;
};

Document parse_to_document(std::string markdown, bool cjk_friendly, bool html,
                           std::shared_ptr<const Schema> schema, ParseObservation* observation = nullptr);

}  // namespace marktip
