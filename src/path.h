#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace marktip {

// Breadcrumb into the input dict, e.g. content[0].content[2].marks[1].
// Segments are static strings so pushing a frame never allocates;
// the path string is only rendered when an error is actually thrown.
struct PathFrame {
    const char* segment;  // "content" | "marks"
    std::size_t index;
};

using PathStack = std::vector<PathFrame>;

inline std::string format_path(const PathStack& path) {
    std::string out;
    for (std::size_t i = 0; i < path.size(); ++i) {
        if (i != 0) {
            out.push_back('.');
        }
        out += path[i].segment;
        out.push_back('[');
        out += std::to_string(path[i].index);
        out.push_back(']');
    }
    return out;
}

}  // namespace marktip
