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

struct ContentFill {
    std::string type;
    std::optional<std::size_t> original;
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
    std::vector<std::string> referenced_types;
    std::vector<std::string> implicit_types;
    std::vector<std::string> required_once_types;

    bool match(const std::vector<std::string_view>& children) const;
    bool idempotent(std::string_view type) const;
    bool accepts_type(std::string_view type) const;
    bool required_once(std::string_view type) const;
    std::optional<std::vector<ContentFill>> fill(const std::vector<std::string_view>& children,
                                                 const std::vector<std::string>& creatable) const;
};

ContentDFA compile_content(std::string_view expression, const std::vector<ContentType>& types);

}  // namespace marktip
