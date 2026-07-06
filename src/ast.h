#pragma once

#include <pybind11/pybind11.h>

#include <cstddef>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

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

// Raised by from_dict when a node or mark type is outside the closed schema.
// Subclasses std::invalid_argument so it surfaces as (a subclass of) ValueError.
class UnknownTypeError : public std::invalid_argument {
public:
    UnknownTypeError(std::string kind, std::string type_name, std::string path)
        : std::invalid_argument("unknown " + kind + " type '" + type_name + "' at " +
                                (path.empty() ? std::string("root") : path)),
          kind_(std::move(kind)),
          type_name_(std::move(type_name)),
          path_(std::move(path)) {}

    const std::string& kind() const noexcept { return kind_; }
    const std::string& type_name() const noexcept { return type_name_; }
    const std::string& path() const noexcept { return path_; }

private:
    std::string kind_;       // "node" | "mark"
    std::string type_name_;
    std::string path_;       // "content[0].marks[1]"; empty = root
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
