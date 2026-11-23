#pragma once

#include "md4c.h"
#include "parser.h"

namespace marktip {

struct NodeSpec;

class MarkdownParser {
public:
    MarkdownParser(ParseOptions options, std::shared_ptr<const Schema> schema);
    MarkdownParser(const MarkdownParser&) = delete;
    MarkdownParser& operator=(const MarkdownParser&) = delete;

    Document parse(std::string markdown, const NodeSpec* detached_textblock = nullptr) const;

private:
    ParseOptions options_;
    std::shared_ptr<const Schema> schema_;
    std::vector<MD_TYPED_TAG> typed_tags_;
    MD_PARSER parser_ {};
    bool needs_lift_;
};

}  // namespace marktip
