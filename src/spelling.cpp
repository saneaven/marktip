#include "spelling.h"

#include <utility>

namespace marktip {

Spelling::Spelling(std::string input) : source(std::make_shared<const std::string>(std::move(input))) {}

Spelling::Spelling(std::shared_ptr<const std::string> input) : source(std::move(input)) {}

std::string_view Spelling::view(SourceRange range) const {
    return std::string_view(*source).substr(range.begin, range.end - range.begin);
}

void Spelling::append_segment(std::size_t begin, std::size_t end, bool has_node) {
    // Find the last nonblank line, then keep its trailing spaces before its terminator.
    std::size_t text_end = end;
    while (text_end > begin) {
        char ch = (*source)[text_end - 1];
        if (ch != ' ' && ch != '\t' && ch != '\r' && ch != '\n') {
            break;
        }
        --text_end;
    }
    while (text_end < end && (*source)[text_end] != '\r' && (*source)[text_end] != '\n') {
        ++text_end;
    }
    items.push_back({SourceRange {begin, text_end}, {text_end, end}, has_node});
}

Spelling restore_spelling(const StoredSpelling& stored) {
    std::string source = stored.head;
    std::vector<SpellingPiece> pieces;
    pieces.reserve(stored.items.size());
    for (const StoredPiece& item : stored.items) {
        std::optional<SourceRange> text;
        if (item.text) {
            std::size_t begin = source.size();
            source += *item.text;
            text = SourceRange {begin, source.size()};
        }
        std::size_t gap_begin = source.size();
        source += item.sep;
        pieces.push_back({text, {gap_begin, source.size()}, item.has_node});
    }
    Spelling spelling(std::move(source));
    spelling.head = {0, stored.head.size()};
    spelling.items = std::move(pieces);
    return spelling;
}

}  // namespace marktip
