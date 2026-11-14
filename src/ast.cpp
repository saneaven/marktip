#include "ast.h"
#include "schema.h"

// md4c's named-entity table,
// used to resolve references inside a link href / image src before the URI policy inspects it.
// entity.h is not part of md4c's public API and has no extern "C" guard of its own;
// the coupling is recorded in third_party/md4c/upstream_metadata/README.md.
extern "C" {
#include "entity.h"
}

#include <algorithm>
#include <optional>

namespace py = pybind11;

namespace marktip {
namespace {

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

// CommonMark replaces an insecure NUL with U+FFFD before parsing. from_dict
// has to make the same normalization or a dict write can serialize bytes that
// change the next time its Markdown is parsed. URI fields are deliberately
// excluded by their caller: raw controls there are an unconditional rejection.
std::string normalize_content_string(std::string value) {
    std::size_t nul = value.find('\0');
    if (nul == std::string::npos) {
        return value;
    }

    std::string normalized;
    normalized.reserve(value.size() + 2);
    std::size_t start = 0;
    while (nul != std::string::npos) {
        normalized.append(value, start, nul - start);
        normalized.append("\xEF\xBF\xBD");
        start = nul + 1;
        nul = value.find('\0', start);
    }
    normalized.append(value, start, std::string::npos);
    return normalized;
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

// --- the attr schema --------------------------------------------------------
//
// Which attrs each type may carry, what each may hold, and what is lost by converting it.
// Two readers: attrs_from_py just below, which keeps the values markdown can act on,
// and strict mode further down, which decides which of the losses a caller is willing to take.

// The schema is small enough that a linear scan beats anything cleverer,
// and both readers need the same lookup: nullptr when the type does not declare that attr.
const AttrSpec* find_attr_spec(const std::vector<AttrSpec>& specs, std::string_view name) {
    for (const AttrSpec& spec : specs) {
        if (spec.name == name) {
            return &spec;
        }
    }
    return nullptr;
}

// str, int and bool are the values the serializer can act on; every other key is dropped.
// Stamping the rest through py::str turned [100] into "[100]" and a None into "",
// which put a string the caller never wrote into to_dict() and lost the value anyway.
// Dropping says the same thing without the invention,
// and it is what collapses "None" and "no such key" into one shape for everything downstream:
// strict, the serializer, the URI policy.
AttrList attrs_from_py(py::dict attrs, std::string_view owner_type, bool owner_is_mark) {
    AttrList out;
    for (auto item : attrs) {
        std::string name = py_to_string(item.first);
        py::handle value = item.second;
        if (py::isinstance<py::bool_>(value)) {
            set_attr(out, std::move(name), AttrValue::boolean(py::cast<bool>(value)));
        } else if (py::isinstance<py::int_>(value)) {
            set_attr(out, std::move(name), AttrValue::integer(py::cast<long long>(value)));
        } else if (py::isinstance<py::str>(value)) {
            bool is_uri = (owner_is_mark && owner_type == "link" && name == "href") ||
                          (!owner_is_mark && owner_type == "image" && name == "src");
            std::string string_value = py::cast<std::string>(value);
            if (!is_uri) {
                string_value = normalize_content_string(std::move(string_value));
            }
            set_attr(out, std::move(name), AttrValue::string(std::move(string_value)));
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

// --- strict mode ------------------------------------------------------------
//
// Node and mark *types* are always closed, while strict additionally closes
// their top-level fields, content models and attrs. Without it, a field or attr
// the serializer never reads is dropped without a word.
// strict names what a caller refuses to lose, from the walk that is already
// happening, so a consumer does not have to re-traverse the tree in Python just
// to find out whether the document survives conversion intact.
//
// Content and Exact differ over one thing, the Dropped attrs,
// and they differ because nothing in the JSON says whether a `target: "_blank"` was chosen or stamped on:
// ProseMirror serializes schema defaults onto every node, so both spellings arrive identical.
// A caller storing markdown as the record wants Content; one keeping the JSON wants Exact.
//
// The attr check reads the raw py::dict rather than the built AttrList,
// because attrs_from_py has already dropped a None and anything it cannot carry
// by then. That also makes it from_dict-only, which is the whole story anyway —
// the parser emits nothing but attrs it knows about, in range,
// so there is nothing for from_markdown to catch.

void check_top_level_fields(py::dict value, std::string_view owner_type, const char* kind,
                            bool inline_type, const PathStack& path) {
    for (auto item : value) {
        std::string name = py_to_string(item.first);
        bool allowed = name == "type" || name == "attrs";
        if (std::string_view(kind) == "mark") {
            if (!allowed) {
                throw InvalidNodeError("unknown_field", name,
                                       "field '" + name + "' is not defined for mark type '" + std::string(owner_type) +
                                           "'",
                                       format_path(path));
            }
            continue;
        }

        allowed = allowed || name == "content" || (name == "text" && owner_type == "text") ||
                  (name == "marks" && inline_type);
        if (!allowed) {
            throw InvalidNodeError("unknown_field", name,
                                   "field '" + name + "' is not defined for node type '" + std::string(owner_type) +
                                       "'",
                                   format_path(path));
        }
    }
}

void check_text_payload(py::dict node_dict, const PathStack& path) {
    if (!dict_contains(node_dict, "text")) {
        throw InvalidNodeError("invalid_content", "text", "text node is missing required field 'text'",
                               format_path(path));
    }
    py::object value = node_dict[py::str("text")];
    if (!py::isinstance<py::str>(value)) {
        throw InvalidNodeError("invalid_content", "text", "text node field 'text' must be a str", format_path(path));
    }
    if (py::cast<std::string>(value).empty()) {
        throw InvalidNodeError("invalid_content", "text", "text node field 'text' must not be empty",
                               format_path(path));
    }
}

// Out-of-range values (10 ** 100) come back false rather than raising, so they report as
// a document problem with a path, not as an unlocated OverflowError.
bool as_int(py::handle value, long long& out) {
    int overflow = 0;
    long long result = PyLong_AsLongLongAndOverflow(value.ptr(), &overflow);
    if (overflow != 0 || (result == -1 && PyErr_Occurred() != nullptr)) {
        PyErr_Clear();
        return false;
    }
    out = result;
    return true;
}

// py::bool_ is a subclass of py::int_, so every integer rule has to exclude it first.
bool is_plain_int(py::handle value) {
    return py::isinstance<py::int_>(value) && !py::isinstance<py::bool_>(value);
}

void check_attr_value(py::handle value, AttrRule rule, const std::string& name, const PathStack& path) {
    auto expected = [&](const char* what) {
        throw InvalidNodeError("invalid_attr_value", name, "attr '" + name + "' must be " + what,
                               format_path(path));
    };
    auto unrepresentable = [&](const char* why) {
        throw InvalidNodeError("unrepresentable", name,
                               "attr '" + name + "' cannot be expressed in markdown: " + why, format_path(path));
    };

    long long number = 0;
    switch (rule) {
        case AttrRule::Str:
            if (!py::isinstance<py::str>(value)) {
                expected("a str");
            }
            return;
        case AttrRule::InfoStr:
            if (!py::isinstance<py::str>(value)) {
                expected("a str");
            }
            if (py::cast<std::string>(value).find_first_of("\r\n") != std::string::npos) {
                expected("a single line");
            }
            return;
        case AttrRule::Bool:
            if (!py::isinstance<py::bool_>(value)) {
                expected("a bool");
            }
            return;
        case AttrRule::Level:
            if (!is_plain_int(value) || !as_int(value, number) || number < 1 || number > 6) {
                expected("an int between 1 and 6");
            }
            return;
        case AttrRule::ListStart:
            if (!is_plain_int(value) || !as_int(value, number) || number < 0 || number > kMaxListStart) {
                expected("an int between 0 and 999999999");
            }
            return;
        case AttrRule::Count:
            if (!is_plain_int(value) || !as_int(value, number) || number < 0) {
                expected("a non-negative int");
            }
            return;
        case AttrRule::Align:
            if (value.is_none()) {
                return;
            }
            if (!py::isinstance<py::str>(value)) {
                expected("'left', 'center', 'right' or None");
            }
            {
                std::string align = py::cast<std::string>(value);
                if (align != "left" && align != "center" && align != "right") {
                    expected("'left', 'center', 'right' or None");
                }
            }
            return;
        case AttrRule::Size:
            if (!py::isinstance<py::str>(value) && !is_plain_int(value)) {
                expected("a str or an int");
            }
            return;
        case AttrRule::ColWidth:
            if (!py::isinstance<py::list>(value)) {
                expected("a list of ints");
            }
            for (py::handle item : py::reinterpret_borrow<py::list>(value)) {
                if (!is_plain_int(item) || !as_int(item, number)) {
                    expected("a list of ints");
                }
            }
            return;
        case AttrRule::NoSpan:
            if (!is_plain_int(value) || !as_int(value, number)) {
                expected("an int");
            }
            if (number != 1) {
                unrepresentable("GFM tables have no cell spanning");
            }
            return;
    }
}

void check_attrs_strict(py::dict attrs, const std::vector<AttrSpec>& specs, std::string_view owner_type,
                        const char* kind, StrictMode mode, const PathStack& path) {
    for (auto item : attrs) {
        std::string name = py_to_string(item.first);
        const AttrSpec* spec = find_attr_spec(specs, name);
        if (spec == nullptr) {
            // Outside both dialects: a typo, or a key an app invented and expects to survive.
            throw InvalidNodeError("unknown_attr", name,
                                   "attr '" + name + "' is not defined for " + kind + " type '" +
                                       std::string(owner_type) + "'",
                                   format_path(path));
        }
        // Unset rather than wrongly typed: this is what the editor submits for an attr
        // nobody filled in, so refusing it would refuse ordinary editor output.
        // A Refused attr still fails the value rule below —
        // Tiptap gives those a non-null default and never emits a null for one,
        // so a null there is a caller bug worth reporting even though the conversion survives it.
        if (spec->null == NullAttr::Unset && item.second.is_none()) {
            continue;
        }
        // Refused before the value is looked at: under Exact the name alone settles it,
        // and a caller who will not lose a width does not need to hear that this one is malformed too.
        if (spec->form == MarkdownForm::Dropped && mode == StrictMode::Exact) {
            throw InvalidNodeError("unrepresentable", name,
                                   "attr '" + name + "' cannot be expressed in markdown: " + spec->why,
                                   format_path(path));
        }
        check_attr_value(item.second, spec->rule, name, path);
    }
}

// Reads the built AttrList rather than the input dict, so "no such key" and "the key is None"
// arrive here as one case — attrs_from_py has already dropped the None.
// A node carrying no attrs dict at all is the third spelling, which is why the caller
// runs this outside its `attrs` block.
void check_required_attrs(const AttrList& attrs, const std::vector<AttrSpec>& specs, std::string_view owner_type,
                          const char* kind, const PathStack& path) {
    for (const AttrSpec& spec : specs) {
        if (spec.presence != Presence::Required || find_attr(attrs, spec.name) != nullptr) {
            continue;
        }
        std::string name(spec.name);
        throw InvalidNodeError("missing_attr", name,
                               "attr '" + name + "' is required for " + kind + " type '" +
                                   std::string(owner_type) + "'",
                               format_path(path));
    }
}

Mark mark_from_py(py::dict mark_dict, const Schema& schema, StrictMode mode, const PathStack& path) {
    Mark mark;
    mark.type = required_type(mark_dict, "mark", path);
    const MarkSpec* spec = schema.mark(mark.type);
    if (spec == nullptr) {
        throw UnknownTypeError("mark", mark.type, format_path(path));
    }
    if (mode != StrictMode::Off) {
        check_top_level_fields(mark_dict, mark.type, "mark", false, path);
    }

    const std::vector<AttrSpec>& specs = spec->attrs;
    py::object attrs = dict_get(mark_dict, "attrs");
    if (!attrs.is_none() || (mode != StrictMode::Off && dict_contains(mark_dict, "attrs"))) {
        py::dict attr_dict = expect_dict(attrs, "mark attrs", "attrs", path);
        if (mode != StrictMode::Off) {
            check_attrs_strict(attr_dict, specs, mark.type, "mark", mode, path);
        }
        mark.attrs = attrs_from_py(attr_dict, mark.type, true);
    }
    // Outside the block above on purpose: a link mark with no attrs key at all
    // is a link with no destination just as much as one whose href is None.
    if (mode != StrictMode::Off) {
        check_required_attrs(mark.attrs, specs, mark.type, "mark", path);
    }

    return mark;
}

// Keep mark parsing outside fill_node_from_py's recursive frame: kMaxNodeDepth must
// remain safe on the smaller Windows worker stack even as strict checks grow.
void fill_marks_from_py(Node& node, py::object marks, const Schema& schema, StrictMode mode, PathStack& path) {
    if (marks.is_none()) {
        return;
    }

    py::list mark_list = expect_list(marks, "node marks", "marks", path);
    std::size_t mark_index = 0;
    for (py::handle mark_handle : mark_list) {
        path.push_back({"marks", mark_index});
        Mark mark = mark_from_py(expect_dict(mark_handle, "mark", "marks", path), schema, mode, path);
        if (mode != StrictMode::Off) {
            // Marktip's standard ProseMirror marks are self-exclusive. This is a strict
            // semantic check: Off intentionally stores the collection exactly as supplied.
            bool conflicts = std::any_of(node.marks.begin(), node.marks.end(), [&](const Mark& existing) {
                return existing.type == mark.type;
            });
            if (conflicts) {
                throw InvalidNodeError("invalid_mark_set", "marks",
                                       "mark type '" + mark.type +
                                           "' conflicts with an earlier mark of the same type",
                                       format_path(path));
            }
        }
        node.marks.push_back(std::move(mark));
        path.pop_back();
        ++mark_index;
    }
}

// Keep node field/attr/mark parsing outside fill_node_from_py's recursive
// frame. kMaxNodeDepth must remain safe on small Windows worker stacks even as
// strict validation grows.
const NodeSpec* fill_node_fields_from_py(Document& document, std::size_t index, py::dict node_dict,
                                         std::string_view context, StrictMode mode, PathStack& path) {
    Node node;
    node.type = required_type(node_dict, context, path);
    const Schema& schema = document.schema();
    const NodeSpec* spec = schema.node(node.type);
    if (spec == nullptr) {
        throw UnknownTypeError("node", node.type, format_path(path));
    }

    if (mode != StrictMode::Off) {
        check_top_level_fields(node_dict, node.type, "node", spec->is_inline, path);
        if (node.type == "text") {
            check_text_payload(node_dict, path);
        }
    }

    if (node.type == "text") {
        node.text = normalize_content_string(py_to_string(dict_get(node_dict, "text")));
    }

    const std::vector<AttrSpec>& specs = spec->attrs;
    py::object attrs = dict_get(node_dict, "attrs");
    if (!attrs.is_none() || (mode != StrictMode::Off && dict_contains(node_dict, "attrs"))) {
        py::dict attr_dict = expect_dict(attrs, "node attrs", "attrs", path);
        if (mode != StrictMode::Off) {
            check_attrs_strict(attr_dict, specs, node.type, "node", mode, path);
        }
        node.attrs = attrs_from_py(attr_dict, node.type, false);
    }
    // Outside the block above: an image with no attrs key at all still has no src.
    if (mode != StrictMode::Off) {
        check_required_attrs(node.attrs, specs, node.type, "node", path);
    }

    py::object marks = dict_get(node_dict, "marks");
    if (mode != StrictMode::Off && marks.is_none() && dict_contains(node_dict, "marks")) {
        expect_list(marks, "node marks", "marks", path);
    }
    fill_marks_from_py(node, marks, schema, mode, path);

    document.node(index) = std::move(node);
    return spec;
}

const NodeSpec* fill_node_from_py(Document& document, std::size_t index, py::dict node_dict, std::string_view context,
                                  std::size_t depth, StrictMode mode, PathStack& path) {
    if (depth > kMaxNodeDepth) {
        throw InvalidNodeError("max_depth", "content", "node content nesting exceeds maximum depth",
                               format_path(path));
    }

    const NodeSpec* spec = fill_node_fields_from_py(document, index, node_dict, context, mode, path);
    const std::string& node_type = spec->name;

    bool has_content = dict_contains(node_dict, "content");
    py::object content = dict_get(node_dict, "content");
    if (!has_content || (content.is_none() && mode == StrictMode::Off)) {
        return spec;
    }

    py::list content_list = expect_list(content, "node content", "content", path);
    ContentModel content_model = spec->allow;
    if (mode != StrictMode::Off && content_model == ContentModel::None) {
        throw InvalidNodeError("invalid_content", "content", "node type '" + node_type + "' must not carry content",
                               format_path(path));
    }
    std::size_t child_pos = 0;
    for (py::handle child_handle : content_list) {
        path.push_back({"content", child_pos});
        py::dict child_dict = expect_dict(child_handle, "content child", "content", path);
        std::size_t child_index = document.append_child(index, Node{});
        const NodeSpec* child = fill_node_from_py(document, child_index, child_dict, "node", depth + 1, mode, path);
        if (mode != StrictMode::Off) {
            if (!document.schema().content_model_allows(content_model, *child)) {
                throw InvalidNodeError("invalid_content", "content",
                                       "node type '" + node_type + "' cannot contain node type '" + child->name + "'",
                                       format_path(path));
            }
            if (node_type == "codeBlock" && !document.node(child_index).marks.empty()) {
                throw InvalidNodeError("invalid_content", "marks", "text inside codeBlock must not carry marks",
                                       format_path(path));
            }
        }
        path.pop_back();
        ++child_pos;
    }
    return spec;
}

// --- URI policy -------------------------------------------------------------
//
// Enforced against the finished Document,
// rather than inlined into from_dict's walk and the parser's callbacks,
// so both write boundaries report the same .code/.field/.path from one implementation.
// It is also the only way from_markdown gets a located error at all:
// MD4C's callbacks are noexcept,
// so anything thrown from inside one comes back out as a bare ParseError with no .path/.field
// (see parser.cpp).
//
// The check resolves entity references itself (decode_entities below).
// MD4C does not: it reports MD_TEXT_ENTITY substrings but leaves them verbatim in MD_ATTRIBUTE,
// so "&#106;avascript:alert(1)" is what actually lands in the href —
// still a javascript URL once a consumer renders it into HTML.

bool is_scheme_alpha(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}

bool is_scheme_char(char c) {
    return is_scheme_alpha(c) || (c >= '0' && c <= '9') || c == '+' || c == '-' || c == '.';
}

bool has_control_char(std::string_view value) {
    for (unsigned char c : value) {
        if (c < 0x20 || c == 0x7F) {
            return true;
        }
    }
    return false;
}

std::string ascii_lower(std::string_view value) {
    std::string out(value);
    for (char& c : out) {
        if (c >= 'A' && c <= 'Z') {
            c = static_cast<char>(c - 'A' + 'a');
        }
    }
    return out;
}

bool is_valid_scheme(std::string_view value) {
    if (value.empty() || !is_scheme_alpha(value.front())) {
        return false;
    }
    for (std::size_t i = 1; i < value.size(); ++i) {
        if (!is_scheme_char(value[i])) {
            return false;
        }
    }
    return true;
}

// Browsers strip leading spaces before reading the scheme,
// so " javascript:x" is a javascript URL and must be treated as one.
// Every other whitespace byte is a control character,
// and has already been rejected by the time this runs.
std::string_view strip_leading_spaces(std::string_view value) {
    std::size_t start = value.find_first_not_of(' ');
    return start == std::string_view::npos ? std::string_view {} : value.substr(start);
}

// RFC 3986: scheme = ALPHA *( ALPHA / DIGIT / "+" / "-" / "." ) ":"
// Returns the lowercased scheme, or nullopt for a relative reference.
std::optional<std::string> scheme_of(std::string_view value) {
    value = strip_leading_spaces(value);
    if (value.empty() || !is_scheme_alpha(value.front())) {
        return std::nullopt;
    }
    std::size_t end = 1;
    while (end < value.size() && is_scheme_char(value[end])) {
        ++end;
    }
    if (end >= value.size() || value[end] != ':') {
        return std::nullopt;
    }
    return ascii_lower(value.substr(0, end));
}

// "//host/x" carries no scheme but still leaves the origin.
// Browsers fold backslashes into slashes for special schemes,
// so "\\host/x" and "/\host/x" resolve the same way,
// and have to count as protocol-relative too.
bool is_protocol_relative(std::string_view value) {
    value = strip_leading_spaces(value);
    if (value.size() < 2) {
        return false;
    }
    auto is_slash = [](char c) { return c == '/' || c == '\\'; };
    return is_slash(value[0]) && is_slash(value[1]);
}

void append_utf8(unsigned codepoint, std::string& out) {
    if (codepoint < 0x80) {
        out.push_back(static_cast<char>(codepoint));
    } else if (codepoint < 0x800) {
        out.push_back(static_cast<char>(0xC0 | (codepoint >> 6)));
        out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    } else if (codepoint < 0x10000) {
        out.push_back(static_cast<char>(0xE0 | (codepoint >> 12)));
        out.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    } else {
        out.push_back(static_cast<char>(0xF0 | (codepoint >> 18)));
        out.push_back(static_cast<char>(0x80 | ((codepoint >> 12) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    }
}

// `body` is what sits between '&' and ';', starting with '#'.
bool append_numeric_entity(std::string_view body, std::string& out) {
    std::size_t i = 1;
    unsigned base = 10;
    if (i < body.size() && (body[i] == 'x' || body[i] == 'X')) {
        base = 16;
        ++i;
    }
    if (i >= body.size()) {
        return false;
    }

    unsigned long long value = 0;
    bool overflow = false;
    for (; i < body.size(); ++i) {
        char c = body[i];
        unsigned digit;
        if (c >= '0' && c <= '9') {
            digit = static_cast<unsigned>(c - '0');
        } else if (base == 16 && c >= 'a' && c <= 'f') {
            digit = static_cast<unsigned>(c - 'a') + 10;
        } else if (base == 16 && c >= 'A' && c <= 'F') {
            digit = static_cast<unsigned>(c - 'A') + 10;
        } else {
            return false;
        }
        if (!overflow) {
            value = value * base + digit;
            overflow = value > 0x10FFFF;
        }
    }

    // Same substitution the HTML spec makes:
    // NUL, surrogates and out-of-range values render as U+FFFD rather than as the raw codepoint.
    unsigned codepoint = static_cast<unsigned>(value);
    if (overflow || codepoint == 0 || (codepoint >= 0xD800 && codepoint <= 0xDFFF)) {
        codepoint = 0xFFFD;
    }
    append_utf8(codepoint, out);
    return true;
}

// `entity` includes the '&' and the ';': that is md4c's table key format ("&amp;").
bool append_named_entity(std::string_view entity, std::string& out) {
    const ENTITY* found = entity_lookup(entity.data(), entity.size());
    if (found == nullptr) {
        return false;
    }
    append_utf8(found->codepoints[0], out);
    if (found->codepoints[1] != 0) {
        append_utf8(found->codepoints[1], out);
    }
    return true;
}

// Offset of the ';' closing an entity that starts at value[0] == '&', or npos.
//
// The terminator is found by consuming the characters an entity may contain,
// rather than by searching ahead for a ';':
// a query string full of separators and no semicolon at all ("?a=1&b=2&c=3...")
// would otherwise rescan the tail for every '&'.
// A fixed-size window would do that too,
// but numeric references have no length limit —
// "&#0000000000000000000000000106;" is still 'j' to a browser —
// so only the named branch can be capped.
std::size_t entity_semicolon(std::string_view value) {
    auto is_digit = [](char c) { return c >= '0' && c <= '9'; };
    auto is_hex = [&](char c) { return is_digit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'); };

    std::size_t i = 1;
    if (i < value.size() && value[i] == '#') {
        ++i;
        if (i < value.size() && (value[i] == 'x' || value[i] == 'X')) {
            ++i;
            while (i < value.size() && is_hex(value[i])) {
                ++i;
            }
        } else {
            while (i < value.size() && is_digit(value[i])) {
                ++i;
            }
        }
    } else {
        // Every HTML5 named reference is ASCII alphanumeric;
        // the longest, "CounterClockwiseContourIntegral", is 31 characters.
        constexpr std::size_t kMaxNamedEntity = 32;
        std::size_t stop = std::min(value.size(), 1 + kMaxNamedEntity);
        while (i < stop && (is_digit(value[i]) || is_scheme_alpha(value[i]))) {
            ++i;
        }
    }

    if (i > 1 && i < value.size() && value[i] == ';') {
        return i;
    }
    return std::string_view::npos;
}

// Resolves entity references the way a renderer will.
//
// The policy has to run on the decoded form.
// MD4C hands entity substrings through verbatim,
// so "&#106;avascript:alert(1)" is what actually reaches the AST —
// and it is still "javascript:alert(1)" the moment a consumer drops it into an HTML attribute.
// An allowlist that this walks straight through is not an allowlist.
// Single pass, like a browser: "&amp;#106;" yields "&#106;" and stops there.
//
// Only the check sees the decoded form;
// the stored attr keeps its original text, so serialization and round-tripping are untouched.
std::string decode_entities(std::string_view value) {
    std::string out;
    out.reserve(value.size());
    std::size_t i = 0;
    while (i < value.size()) {
        std::size_t end = std::string_view::npos;
        if (value[i] == '&') {
            std::size_t offset = entity_semicolon(value.substr(i));
            if (offset != std::string_view::npos) {
                end = i + offset;
            }
        }
        if (end == std::string_view::npos) {
            out.push_back(value[i]);
            ++i;
            continue;
        }

        std::string_view body = value.substr(i + 1, end - i - 1);
        bool decoded = false;
        if (body.empty()) {
            decoded = false;
        } else if (body.front() == '#') {
            decoded = append_numeric_entity(body, out);
        } else {
            decoded = append_named_entity(value.substr(i, end - i + 1), out);
        }

        if (decoded) {
            i = end + 1;
        } else {
            out.push_back(value[i]);
            ++i;
        }
    }
    return out;
}

void check_uri(std::string_view raw, const UriRule& rule, const char* what, const char* field,
               const PathStack& path) {
    // Decoding is skipped entirely when there is no '&', which is the common case.
    std::string decoded;
    std::string_view value = raw;
    if (raw.find('&') != std::string_view::npos) {
        decoded = decode_entities(raw);
        value = decoded;
    }

    // Unconditional, policy or not:
    // a control character is never valid in a URI unencoded,
    // and leaving one in would bypass the allowlist itself,
    // since browsers drop tab/LF/CR before reading the scheme ("java\tscript:").
    if (has_control_char(value)) {
        throw InvalidNodeError("invalid_uri_char", field, std::string(what) + " contains an ASCII control character",
                               format_path(path));
    }

    std::optional<std::string> scheme = scheme_of(value);
    if (!scheme.has_value()) {
        if (rule.relative == RelativePolicy::Reject) {
            throw InvalidNodeError("disallowed_relative_url", field,
                                   std::string(what) + " must not be a relative reference", format_path(path));
        }
        if (rule.relative == RelativePolicy::PathOnly && is_protocol_relative(value)) {
            throw InvalidNodeError("disallowed_relative_url", field,
                                   std::string(what) + " must not be a protocol-relative reference",
                                   format_path(path));
        }
        return;
    }

    if (rule.restrict_schemes && !std::binary_search(rule.schemes.begin(), rule.schemes.end(), *scheme)) {
        throw InvalidNodeError("disallowed_scheme", field,
                               std::string(what) + " scheme '" + *scheme + "' is not allowed", format_path(path));
    }
}

void check_uri_attr(const AttrList& attrs, const char* key, const UriRule& rule, const char* what,
                    const PathStack& path) {
    const AttrValue* attr = find_attr(attrs, key);
    if (attr == nullptr) {
        return;  // a missing href/src stays accepted; the serializer substitutes a default
    }
    if (attr->kind == AttrValue::Kind::String) {
        check_uri(attr->string_value, rule, what, key, path);
        return;
    }
    // An int/bool href is odd but reachable: from_dict coerces attr values.
    check_uri(attr_string(attrs, key), rule, what, key, path);
}

void enforce_node(const Document& document, std::size_t index, const UriPolicy& policy, PathStack& path) {
    const Node& node = document.node(index);

    if (node.type == "image") {
        check_uri_attr(node.attrs, "src", policy.image, "image src", path);
    }

    // Frame order mirrors fill_node_from_py — marks, then content —
    // so the same violation reports the same .path whichever entry point built the tree.
    for (std::size_t i = 0; i < node.marks.size(); ++i) {
        if (node.marks[i].type != "link") {
            continue;
        }
        path.push_back({"marks", i});
        check_uri_attr(node.marks[i].attrs, "href", policy.link, "link href", path);
        path.pop_back();
    }

    for (std::size_t i = 0; i < node.content.size(); ++i) {
        path.push_back({"content", i});
        enforce_node(document, node.content[i], policy, path);
        path.pop_back();
    }
}

void enforce_rejected_node_types(const Document& document, std::size_t index, const NodeTypePolicy& policy,
                                 PathStack& path) {
    const Node& node = document.node(index);
    if (std::binary_search(policy.rejected.begin(), policy.rejected.end(), node.type)) {
        throw InvalidNodeError("disallowed_node_type", "type", "node type '" + node.type + "' is not allowed",
                               format_path(path));
    }
    for (std::size_t i = 0; i < node.content.size(); ++i) {
        path.push_back({"content", i});
        enforce_rejected_node_types(document, node.content[i], policy, path);
        path.pop_back();
    }
}

// Spelled like the relative policy below rather than as a bool,
// because the interesting question has three answers and only one of them is "do not check".
StrictMode strict_from_py(py::handle value, const char* arg_name) {
    if (!py::isinstance<py::str>(value)) {
        throw py::type_error(std::string(arg_name) + " must be a str");
    }
    std::string level = py::cast<std::string>(value);
    if (level == "off") {
        return StrictMode::Off;
    }
    if (level == "content") {
        return StrictMode::Content;
    }
    if (level == "exact") {
        return StrictMode::Exact;
    }
    throw py::value_error(std::string(arg_name) + " must be 'off', 'content' or 'exact', not '" + level + "'");
}

RelativePolicy relative_from_py(py::handle value, const char* arg_name) {
    if (!py::isinstance<py::str>(value)) {
        throw py::type_error(std::string(arg_name) + " must be a str");
    }
    std::string mode = py::cast<std::string>(value);
    if (mode == "allow") {
        return RelativePolicy::Allow;
    }
    if (mode == "path_only") {
        return RelativePolicy::PathOnly;
    }
    if (mode == "reject") {
        return RelativePolicy::Reject;
    }
    throw py::value_error(std::string(arg_name) + " must be 'allow', 'path_only' or 'reject', not '" + mode + "'");
}

void schemes_from_py(py::handle value, const char* arg_name, UriRule& rule) {
    if (value.is_none()) {
        return;  // no restriction: every scheme is allowed, which is the default
    }
    if (py::isinstance<py::str>(value) || py::isinstance<py::bytes>(value)) {
        // Iterating a bare "https" would silently build the set {h, t, p, s}.
        throw py::type_error(std::string(arg_name) + " must be an iterable of str, not a single str");
    }

    // An empty iterable is meaningful and distinct from None:
    // it allows no scheme at all, leaving only whatever the relative policy permits.
    rule.restrict_schemes = true;
    for (py::handle item : py::reinterpret_borrow<py::object>(value)) {
        if (!py::isinstance<py::str>(item)) {
            throw py::type_error(std::string(arg_name) + " entries must be str");
        }
        std::string scheme = ascii_lower(py::cast<std::string>(item));
        if (!is_valid_scheme(scheme)) {
            throw py::value_error(std::string(arg_name) + " entry '" + scheme +
                                  "' is not a scheme name (expected e.g. 'https', not 'https://')");
        }
        rule.schemes.push_back(std::move(scheme));
    }
    std::sort(rule.schemes.begin(), rule.schemes.end());
    rule.schemes.erase(std::unique(rule.schemes.begin(), rule.schemes.end()), rule.schemes.end());
}

void rejected_node_types_from_py(py::handle value, const char* arg_name, const Schema& schema,
                                 NodeTypePolicy& policy) {
    if (value.is_none()) {
        return;
    }
    if (py::isinstance<py::str>(value) || py::isinstance<py::bytes>(value)) {
        throw py::type_error(std::string(arg_name) + " must be an iterable of str, not a single str");
    }

    for (py::handle item : py::reinterpret_borrow<py::object>(value)) {
        if (!py::isinstance<py::str>(item)) {
            throw py::type_error(std::string(arg_name) + " entries must be str");
        }
        std::string type = py::cast<std::string>(item);
        if (schema.node(type) == nullptr) {
            throw py::value_error(std::string(arg_name) + " entry '" + type + "' is not a known node type");
        }
        policy.rejected.push_back(std::move(type));
    }
    std::sort(policy.rejected.begin(), policy.rejected.end());
    policy.rejected.erase(std::unique(policy.rejected.begin(), policy.rejected.end()), policy.rejected.end());
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

Document::Document(std::size_t reserve_size) : schema_(Schema::gfm()) {
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

const Schema& Document::schema() const {
    return *schema_;
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

void enforce_uri_policy(const Document& document, const UriPolicy& policy) {
    PathStack path;
    path.reserve(32);
    enforce_node(document, 0, policy, path);
}

void enforce_node_type_policy(const Document& document, const NodeTypePolicy& policy) {
    if (policy.rejected.empty()) {
        return;
    }
    PathStack path;
    path.reserve(32);
    enforce_rejected_node_types(document, 0, policy, path);
}

UriPolicy uri_policy_from_py(py::object link_schemes, py::object image_schemes, py::object link_relative,
                             py::object image_relative) {
    UriPolicy policy;
    schemes_from_py(link_schemes, "link_schemes", policy.link);
    schemes_from_py(image_schemes, "image_schemes", policy.image);
    policy.link.relative = relative_from_py(link_relative, "link_relative");
    policy.image.relative = relative_from_py(image_relative, "image_relative");
    return policy;
}

NodeTypePolicy node_type_policy_from_py(py::object reject_node_types) {
    NodeTypePolicy policy;
    rejected_node_types_from_py(reject_node_types, "reject_node_types", *Schema::gfm(), policy);
    return policy;
}

Document from_dict_py(py::dict root, py::object link_schemes, py::object image_schemes, py::object link_relative,
                      py::object image_relative, py::object reject_node_types, py::object strict) {
    // Options are validated before the tree is walked:
    // a bad option value is a caller bug,
    // and should surface whatever the document happens to contain.
    UriPolicy policy = uri_policy_from_py(std::move(link_schemes), std::move(image_schemes), std::move(link_relative),
                                          std::move(image_relative));
    NodeTypePolicy node_policy = node_type_policy_from_py(std::move(reject_node_types));
    StrictMode mode = strict_from_py(strict, "strict");

    PathStack path;
    path.reserve(32);

    std::string type = required_type(root, "root node", path);
    if (type != "doc") {
        throw InvalidNodeError("invalid_root", "type", "root node must have type 'doc'", format_path(path));
    }

    Document document;
    fill_node_from_py(document, 0, root, "root node", 0, mode, path);
    enforce_node_type_policy(document, node_policy);
    enforce_uri_policy(document, policy);
    return document;
}

}  // namespace marktip
