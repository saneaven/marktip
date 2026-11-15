#include "spelling.h"

#include <utility>

namespace marktip {

Spelling::Spelling(std::string input) : source(std::make_shared<const std::string>(std::move(input))) {}

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

}  // namespace marktip
