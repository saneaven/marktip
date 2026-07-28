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

// What to do with a link href / image src carrying no scheme at all ("/foo", "#anchor", "./x.png", "").
// PathOnly still rejects protocol-relative references ("//evil.com/x"),
// which have no scheme but do leave the origin.
enum class RelativePolicy { Allow, PathOnly, Reject };

struct UriRule {
    bool restrict_schemes = false;     // false = any scheme is allowed (the default)
    std::vector<std::string> schemes;  // lowercased and sorted, for binary_search
    RelativePolicy relative = RelativePolicy::Allow;
};

// Links and images are governed separately:
// allowing http/mailto for links but only https for images is the common asymmetry.
struct UriPolicy {
    UriRule link;
    UriRule image;
};

// Rejects ASCII control characters in href/src unconditionally,
// then enforces `policy` on top.
// Reads nothing but Node/Mark, which hold no pybind11 objects,
// so this is safe to call with the GIL released (from_markdown does).
void enforce_uri_policy(const Document& document, const UriPolicy& policy);

// Requires the GIL.
// Malformed option values are a caller bug rather than a malformed document,
// so these raise TypeError/ValueError instead of a MarktipError.
UriPolicy uri_policy_from_py(pybind11::object link_schemes, pybind11::object image_schemes,
                             pybind11::object link_relative, pybind11::object image_relative);

Document from_dict_py(pybind11::dict root, pybind11::object link_schemes, pybind11::object image_schemes,
                      pybind11::object link_relative, pybind11::object image_relative);

}  // namespace marktip
