#pragma once

#include <cstddef>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace marktip {

struct SourceRange {
    std::size_t begin = 0;
    std::size_t end = 0;
};

struct SpellingPiece {
    std::optional<SourceRange> text;
    SourceRange gap;
    bool has_node = true;
};

struct StoredPiece {
    std::optional<std::string> text;
    std::string sep;
    bool has_node = true;
};

struct StoredSpelling {
    std::string head;
    std::vector<StoredPiece> items;
};

// Ranges keep the original positions when pieces lose text or change order.
// Sharing the immutable source lets another Document inherit pieces without copying their bytes.
// Pieces that carry a node correspond in order to the root's children.
struct Spelling {
    explicit Spelling(std::string input);
    explicit Spelling(std::shared_ptr<const std::string> input);

    std::shared_ptr<const std::string> source;
    SourceRange head;
    std::vector<SpellingPiece> items;

    std::string_view view(SourceRange range) const;
    void append_segment(std::size_t begin, std::size_t end, bool has_node);
};

Spelling restore_spelling(const StoredSpelling& stored);

}  // namespace marktip
