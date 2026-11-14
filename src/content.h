#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace marktip {

struct ContentType {
    std::string name;
    bool is_inline;
    std::vector<std::string> groups;
};

struct ContentDFA {
    struct Transition {
        std::string type;
        std::size_t next;
    };

    struct State {
        std::vector<Transition> transitions;
        bool accepting = false;
    };

    std::vector<State> states;
    std::optional<bool> inline_content;

    bool match(const std::vector<std::string_view>& children) const;
    bool idempotent(std::string_view type) const;
};

ContentDFA compile_content(std::string_view expression, const std::vector<ContentType>& types);

}  // namespace marktip
