#include "ast.h"

// md4c's named-entity table,
// used to resolve references inside a link href / image src before the URI policy inspects it.
// entity.h is not part of md4c's public API and has no extern "C" guard of its own;
// the coupling is recorded in third_party/md4c/upstream_metadata/README.md.
extern "C" {
#include "entity.h"
}

#include <algorithm>
#include <iterator>
#include <optional>

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

void enforce_uri_policy(const Document& document, const UriPolicy& policy) {
    PathStack path;
    path.reserve(32);
    enforce_node(document, 0, policy, path);
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

Document from_dict_py(py::dict root, py::object link_schemes, py::object image_schemes, py::object link_relative,
                      py::object image_relative) {
    // Options are validated before the tree is walked:
    // a bad option value is a caller bug,
    // and should surface whatever the document happens to contain.
    UriPolicy policy = uri_policy_from_py(std::move(link_schemes), std::move(image_schemes), std::move(link_relative),
                                          std::move(image_relative));

    PathStack path;
    path.reserve(32);

    std::string type = required_type(root, "root node", path);
    if (type != "doc") {
        throw InvalidNodeError("invalid_root", "type", "root node must have type 'doc'", format_path(path));
    }

    Document document;
    fill_node_from_py(document, 0, root, "root node", 0, path);
    enforce_uri_policy(document, policy);
    return document;
}

}  // namespace marktip
