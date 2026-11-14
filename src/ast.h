#pragma once

#include <pybind11/pybind11.h>

#include <cstddef>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "errors.h"
#include "value.h"

namespace marktip {

class Schema;

// Deep documents are traversed recursively (to_dict, to_markdown); cap nesting
// at build time so those traversals cannot overflow the C stack.
inline constexpr std::size_t kMaxNodeDepth = 2048;

struct Node {
    std::string type;
    std::string text;
    AttrList attrs;
    std::vector<Mark> marks;
    std::vector<std::size_t> content;
};

class Document {
public:
    Document();
    explicit Document(std::size_t reserve_size);
    explicit Document(std::shared_ptr<const Schema> schema, std::size_t reserve_size = 32);

    const Node& root() const;
    Node& root();
    const Node& node(std::size_t index) const;
    Node& node(std::size_t index);
    const Schema& schema() const;

    std::size_t append_node(Node node);
    std::size_t append_child(std::size_t parent, Node node);

    void order_marks();
    pybind11::dict to_dict() const;

private:
    std::shared_ptr<const Schema> schema_;
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

// Node types a caller's own ProseMirror dialect refuses even though marktip
// itself knows how to parse and serialize them. Keeping this as a boundary
// policy lets both Markdown and dict inputs report the same located error.
struct NodeTypePolicy {
    std::vector<std::string> rejected;
};

// Rejects ASCII control characters in link href, image src, and declared URI attrs unconditionally,
// then enforces `policy` on top.
// Reads nothing but Node/Mark, which hold no pybind11 objects,
// so this is safe to call with the GIL released (from_markdown does).
void enforce_uri_policy(const Document& document, const UriPolicy& policy);

// Rejects any node whose type appears in `policy`, with a path into the built
// document. Plain C++ data only, so from_markdown may call it with the GIL
// released.
void enforce_node_type_policy(const Document& document, const NodeTypePolicy& policy);

// Requires the GIL.
// Malformed option values are a caller bug rather than a malformed document,
// so these raise TypeError/ValueError instead of a MarktipError.
UriPolicy uri_policy_from_py(pybind11::object link_schemes, pybind11::object image_schemes,
                             pybind11::object link_relative, pybind11::object image_relative);
NodeTypePolicy node_type_policy_from_py(pybind11::object reject_node_types);

// What `strict` promises to preserve, rather than what it happens to accept.
//
// Content sits in the middle because losses are not all one kind:
// a colspan the serializer drops moves every cell after it under a different header,
// while a link target it drops costs the author nothing —
// the editor stamped that one on, and no one wrote it.
// Nothing in the JSON tells those apart (ProseMirror serializes schema defaults onto every node),
// so the caller has to say which loss is acceptable.
enum class StrictMode {
    Off,      // no attr checking at all
    Content,  // content and structure survive; presentation attrs may be dropped
    Exact,    // everything survives; an attr markdown cannot carry is an error
};

// `strict` is from_dict-only: the parser emits only declared fields, valid
// content relationships and attrs it understands, so there is nothing on
// from_markdown to catch.
Document from_dict_py(pybind11::dict root, pybind11::object link_schemes, pybind11::object image_schemes,
                      pybind11::object link_relative, pybind11::object image_relative,
                      pybind11::object reject_node_types, pybind11::object strict, pybind11::object schema);

}  // namespace marktip
