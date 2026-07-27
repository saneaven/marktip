#include "ast.h"

#include <algorithm>
#include <iterator>

namespace py = pybind11;

namespace marktip {
namespace {

// The closed schema: every node/mark type the parser can emit and the
// serializer understands. Sorted byte-wise (uppercase sorts before lowercase,
// e.g. tableCell < tableHeader < tableRow) — required by binary_search; do not
// "alphabetize" case-insensitively.
constexpr std::string_view kKnownNodeTypes[] = {
    "blockquote", "bulletList", "codeBlock",  "doc",         "hardBreak", "heading", "horizontalRule",
    "htmlBlock",  "htmlInline", "image",      "listItem",    "orderedList", "paragraph", "table",
    "tableCell",  "tableHeader", "tableRow",  "taskItem",    "taskList",  "text",
};

constexpr std::string_view kKnownMarkTypes[] = {"bold", "code", "italic", "link", "strike"};

bool is_known_node_type(std::string_view type) {
    return std::binary_search(std::begin(kKnownNodeTypes), std::end(kKnownNodeTypes), type);
}

bool is_known_mark_type(std::string_view type) {
    return std::binary_search(std::begin(kKnownMarkTypes), std::end(kKnownMarkTypes), type);
}

// Breadcrumb into the input dict, e.g. content[0].content[2].marks[1].
// Segments are static strings so pushing a frame never allocates; the path
// string is only rendered when an error is actually thrown.
struct PathFrame {
    const char* segment;  // "content" | "marks"
    std::size_t index;
};

using PathStack = std::vector<PathFrame>;

std::string format_path(const PathStack& path) {
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

bool dict_contains(py::dict dict, const char* key) {
    return PyMapping_HasKeyString(dict.ptr(), key) == 1;
}

py::object dict_get(py::dict dict, const char* key) {
    if (!dict_contains(dict, key)) {
        return py::none();
    }
    return dict[py::str(key)];
}

py::dict expect_dict(py::handle value, std::string_view context, const char* field, const PathStack& path) {
    if (!py::isinstance<py::dict>(value)) {
        throw InvalidNodeError("wrong_type", field, std::string(context) + " must be a dict", format_path(path));
    }
    return py::reinterpret_borrow<py::dict>(value);
}

py::list expect_list(py::handle value, std::string_view context, const char* field, const PathStack& path) {
    if (!py::isinstance<py::list>(value)) {
        throw InvalidNodeError("wrong_type", field, std::string(context) + " must be a list", format_path(path));
    }
    return py::reinterpret_borrow<py::list>(value);
}

std::string py_to_string(py::handle value) {
    if (value.is_none()) {
        return "";
    }
    return py::cast<std::string>(py::str(value));
}

std::string required_type(py::dict value, std::string_view context, const PathStack& path) {
    py::object type = dict_get(value, "type");
    if (type.is_none()) {
        throw InvalidNodeError("missing_type", "type", std::string(context) + " is missing required key 'type'",
                               format_path(path));
    }
    return py_to_string(type);
}

py::dict attrs_to_py(const AttrList& attrs) {
    py::dict out;
    for (const auto& attr : attrs) {
        switch (attr.second.kind) {
            case AttrValue::Kind::String:
                out[py::str(attr.first)] = attr.second.string_value;
                break;
            case AttrValue::Kind::Int:
                out[py::str(attr.first)] = attr.second.int_value;
                break;
            case AttrValue::Kind::Bool:
                out[py::str(attr.first)] = attr.second.bool_value;
                break;
        }
    }
    return out;
}

AttrList attrs_from_py(py::dict attrs) {
    AttrList out;
    for (auto item : attrs) {
        std::string key = py_to_string(item.first);
        py::handle value = item.second;
        if (py::isinstance<py::bool_>(value)) {
            set_attr(out, std::move(key), AttrValue::boolean(py::cast<bool>(value)));
        } else if (py::isinstance<py::int_>(value)) {
            set_attr(out, std::move(key), AttrValue::integer(py::cast<long long>(value)));
        } else if (py::isinstance<py::str>(value)) {
            set_attr(out, std::move(key), AttrValue::string(py::cast<std::string>(value)));
        } else {
            set_attr(out, std::move(key), AttrValue::string(py_to_string(value)));
        }
    }
    return out;
}

py::dict mark_to_py(const Mark& mark) {
    py::dict out;
    out["type"] = mark.type;
    if (!mark.attrs.empty()) {
        out["attrs"] = attrs_to_py(mark.attrs);
    }
    return out;
}

py::dict node_to_py(const Document& document, std::size_t index) {
    const Node& node = document.node(index);
    py::dict out;
    out["type"] = node.type;

    if (node.type == "text") {
        out["text"] = node.text;
    }

    if (!node.attrs.empty()) {
        out["attrs"] = attrs_to_py(node.attrs);
    }

    if (!node.marks.empty()) {
        py::list marks;
        for (const auto& mark : node.marks) {
            marks.append(mark_to_py(mark));
        }
        out["marks"] = marks;
    }

    if (node.type == "doc" || !node.content.empty()) {
        py::list content;
        for (std::size_t child : node.content) {
            content.append(node_to_py(document, child));
        }
        out["content"] = content;
    }

    return out;
}

Mark mark_from_py(py::dict mark_dict, const PathStack& path) {
    Mark mark;
    mark.type = required_type(mark_dict, "mark", path);
    if (!is_known_mark_type(mark.type)) {
        throw UnknownTypeError("mark", mark.type, format_path(path));
    }

    py::object attrs = dict_get(mark_dict, "attrs");
    if (!attrs.is_none()) {
        mark.attrs = attrs_from_py(expect_dict(attrs, "mark attrs", "attrs", path));
    }

    return mark;
}

void fill_node_from_py(Document& document, std::size_t index, py::dict node_dict, std::string_view context,
                       std::size_t depth, PathStack& path) {
    if (depth > kMaxNodeDepth) {
        throw InvalidNodeError("max_depth", "content", "node content nesting exceeds maximum depth",
                               format_path(path));
    }

    Node node;
    node.type = required_type(node_dict, context, path);
    if (!is_known_node_type(node.type)) {
        throw UnknownTypeError("node", node.type, format_path(path));
    }

    if (node.type == "text") {
        node.text = py_to_string(dict_get(node_dict, "text"));
    }

    py::object attrs = dict_get(node_dict, "attrs");
    if (!attrs.is_none()) {
        node.attrs = attrs_from_py(expect_dict(attrs, "node attrs", "attrs", path));
    }

    py::object marks = dict_get(node_dict, "marks");
    if (!marks.is_none()) {
        py::list mark_list = expect_list(marks, "node marks", "marks", path);
        std::size_t mark_index = 0;
        for (py::handle mark_handle : mark_list) {
            path.push_back({"marks", mark_index});
            node.marks.push_back(mark_from_py(expect_dict(mark_handle, "mark", "marks", path), path));
            path.pop_back();
            ++mark_index;
        }
    }

    document.node(index) = std::move(node);

    py::object content = dict_get(node_dict, "content");
    if (content.is_none()) {
        return;
    }

    py::list content_list = expect_list(content, "node content", "content", path);
    std::size_t child_pos = 0;
    for (py::handle child_handle : content_list) {
        std::size_t child_index = document.append_child(index, Node{});
        path.push_back({"content", child_pos});
        fill_node_from_py(document, child_index, expect_dict(child_handle, "content child", "content", path), "node",
                          depth + 1, path);
        path.pop_back();
        ++child_pos;
    }
}

}  // namespace

AttrValue AttrValue::string(std::string value) {
    AttrValue attr;
    attr.kind = Kind::String;
    attr.string_value = std::move(value);
    return attr;
}

AttrValue AttrValue::integer(long long value) {
    AttrValue attr;
    attr.kind = Kind::Int;
    attr.int_value = value;
    return attr;
}

AttrValue AttrValue::boolean(bool value) {
    AttrValue attr;
    attr.kind = Kind::Bool;
    attr.bool_value = value;
    return attr;
}

bool AttrValue::operator==(const AttrValue& other) const {
    if (kind != other.kind) {
        return false;
    }
    switch (kind) {
        case Kind::String:
            return string_value == other.string_value;
        case Kind::Int:
            return int_value == other.int_value;
        case Kind::Bool:
            return bool_value == other.bool_value;
    }
    return false;
}

bool Mark::operator==(const Mark& other) const {
    return type == other.type && attrs == other.attrs;
}

void set_attr(AttrList& attrs, std::string key, AttrValue value) {
    for (auto& attr : attrs) {
        if (attr.first == key) {
            attr.second = std::move(value);
            return;
        }
    }
    attrs.emplace_back(std::move(key), std::move(value));
}

const AttrValue* find_attr(const AttrList& attrs, std::string_view key) {
    for (const auto& attr : attrs) {
        if (attr.first == key) {
            return &attr.second;
        }
    }
    return nullptr;
}

std::string attr_string(const AttrList& attrs, std::string_view key, std::string fallback) {
    const AttrValue* attr = find_attr(attrs, key);
    if (attr == nullptr) {
        return fallback;
    }
    if (attr->kind == AttrValue::Kind::String) {
        return attr->string_value;
    }
    if (attr->kind == AttrValue::Kind::Int) {
        return std::to_string(attr->int_value);
    }
    return attr->bool_value ? "true" : "false";
}

long long attr_int(const AttrList& attrs, std::string_view key, long long fallback) {
    const AttrValue* attr = find_attr(attrs, key);
    if (attr == nullptr) {
        return fallback;
    }
    if (attr->kind == AttrValue::Kind::Int) {
        return attr->int_value;
    }
    if (attr->kind == AttrValue::Kind::Bool) {
        return attr->bool_value ? 1 : 0;
    }
    try {
        return std::stoll(attr->string_value);
    } catch (...) {
        return fallback;
    }
}

bool attr_bool(const AttrList& attrs, std::string_view key, bool fallback) {
    const AttrValue* attr = find_attr(attrs, key);
    if (attr == nullptr) {
        return fallback;
    }
    if (attr->kind == AttrValue::Kind::Bool) {
        return attr->bool_value;
    }
    if (attr->kind == AttrValue::Kind::Int) {
        return attr->int_value != 0;
    }
    if (attr->string_value == "true" || attr->string_value == "1") {
        return true;
    }
    if (attr->string_value == "false" || attr->string_value == "0") {
        return false;
    }
    return fallback;
}

Document::Document() : Document(32) {}

Document::Document(std::size_t reserve_size) {
    nodes_.reserve(reserve_size == 0 ? 1 : reserve_size);
    Node root_node;
    root_node.type = "doc";
    nodes_.push_back(std::move(root_node));
}

const Node& Document::root() const {
    return nodes_[0];
}

Node& Document::root() {
    return nodes_[0];
}

const Node& Document::node(std::size_t index) const {
    return nodes_[index];
}

Node& Document::node(std::size_t index) {
    return nodes_[index];
}

std::size_t Document::append_node(Node node) {
    nodes_.push_back(std::move(node));
    return nodes_.size() - 1;
}

std::size_t Document::append_child(std::size_t parent, Node node) {
    std::size_t index = append_node(std::move(node));
    nodes_[parent].content.push_back(index);
    return index;
}

py::dict Document::to_dict() const {
    return node_to_py(*this, 0);
}

Document from_dict_py(py::dict root) {
    PathStack path;
    path.reserve(32);

    std::string type = required_type(root, "root node", path);
    if (type != "doc") {
        throw InvalidNodeError("invalid_root", "type", "root node must have type 'doc'", format_path(path));
    }

    Document document;
    fill_node_from_py(document, 0, root, "root node", 0, path);
    return document;
}

}  // namespace marktip
