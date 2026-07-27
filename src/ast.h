#pragma once

#include <pybind11/pybind11.h>

#include <cstddef>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "errors.h"

namespace marktip {

// Deep documents are traversed recursively (to_dict, to_markdown); cap nesting
// at build time so those traversals cannot overflow the C stack.
inline constexpr std::size_t kMaxNodeDepth = 2048;

struct AttrValue {
    enum class Kind { String, Int, Bool };

    Kind kind = Kind::String;
    std::string string_value;
    long long int_value = 0;
    bool bool_value = false;

    static AttrValue string(std::string value);
    static AttrValue integer(long long value);
    static AttrValue boolean(bool value);

    bool operator==(const AttrValue& other) const;
};

using AttrList = std::vector<std::pair<std::string, AttrValue>>;

struct Mark {
    std::string type;
    AttrList attrs;

    bool operator==(const Mark& other) const;
};

struct Node {
    std::string type;
    std::string text;
    AttrList attrs;
    std::vector<Mark> marks;
    std::vector<std::size_t> content;
};

void set_attr(AttrList& attrs, std::string key, AttrValue value);
const AttrValue* find_attr(const AttrList& attrs, std::string_view key);
std::string attr_string(const AttrList& attrs, std::string_view key, std::string fallback = {});
long long attr_int(const AttrList& attrs, std::string_view key, long long fallback = 0);
bool attr_bool(const AttrList& attrs, std::string_view key, bool fallback = false);

class Document {
public:
    Document();
    explicit Document(std::size_t reserve_size);

    const Node& root() const;
    Node& root();
    const Node& node(std::size_t index) const;
    Node& node(std::size_t index);

    std::size_t append_node(Node node);
    std::size_t append_child(std::size_t parent, Node node);

    pybind11::dict to_dict() const;

private:
    std::vector<Node> nodes_;
};

Document from_dict_py(pybind11::dict root);

}  // namespace marktip
