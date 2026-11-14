#include "policy.h"

#include "ast.h"
#include "compiler.h"
#include "errors.h"
#include "path.h"
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
#include <stdexcept>
#include <utility>

namespace marktip {
namespace {

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

template <typename Describe>
void check_uri_value(std::string_view value, const UriRule& rule, const Describe& describe, const char* field,
                     const PathStack& path) {
    // Unconditional, policy or not:
    // a control character is never valid in a URI unencoded,
    // and leaving one in would bypass the allowlist itself,
    // since browsers drop tab/LF/CR before reading the scheme ("java\tscript:").
    if (has_control_char(value)) {
        throw InvalidNodeError("invalid_uri_char", field, describe() + " contains an ASCII control character",
                               format_path(path));
    }

    std::optional<std::string> scheme = scheme_of(value);
    if (!scheme.has_value()) {
        if (rule.relative == RelativePolicy::Reject) {
            throw InvalidNodeError("disallowed_relative_url", field,
                                   describe() + " must not be a relative reference", format_path(path));
        }
        if (rule.relative == RelativePolicy::PathOnly && is_protocol_relative(value)) {
            throw InvalidNodeError("disallowed_relative_url", field,
                                   describe() + " must not be a protocol-relative reference",
                                   format_path(path));
        }
        return;
    }

    if (rule.restrict_schemes && !std::binary_search(rule.schemes.begin(), rule.schemes.end(), *scheme)) {
        throw InvalidNodeError("disallowed_scheme", field,
                               describe() + " scheme '" + *scheme + "' is not allowed", format_path(path));
    }
}

template <typename Describe>
void check_uri(std::string_view raw, const UriRule& rule, const Describe& describe, const char* field,
               const PathStack& path, bool check_written) {
    // Decoding is skipped entirely when there is no '&', which is the common case.
    std::string decoded;
    std::string_view value = raw;
    if (raw.find('&') != std::string_view::npos) {
        // Tag attrs escape '&', so the stored spelling must pass as well as the decoded form.
        if (check_written) {
            check_uri_value(raw, rule, describe, field, path);
        }
        decoded = decode_entities(raw);
        value = decoded;
    }
    check_uri_value(value, rule, describe, field, path);
}

template <typename Describe>
MARKTIP_NOINLINE void check_uri_attr(const AttrList& attrs, const char* key, const UriRule& rule,
                                    const Describe& describe, const PathStack& path, bool check_written = false) {
    const AttrValue* attr = find_attr(attrs, key);
    if (attr == nullptr) {
        return;  // a missing URI attr stays accepted; strict mode handles required attrs
    }
    if (attr->kind == AttrValue::Kind::String) {
        check_uri(attr->string_value, rule, describe, key, path, check_written);
        return;
    }
    // An int/bool URI is odd but reachable: from_dict coerces attr values.
    check_uri(attr_string(attrs, key), rule, describe, key, path, check_written);
}

void enforce_mark_uri(const Mark& mark, const Schema& schema, const UriPolicy& policy, const PathStack& path) {
    const MarkSpec& spec = *schema.mark(mark.type);
    for (const AttrSpec& attr : spec.attrs) {
        if (attr.uri == UriKind::None) {
            continue;
        }
        const UriRule& rule = attr.uri == UriKind::Link ? policy.link : policy.image;
        auto describe = [&]() { return "mark type '" + mark.type + "' attr '" + attr.name + "'"; };
        check_uri_attr(mark.attrs, attr.name.c_str(), rule, describe, path, true);
    }
}

// Keep mark URI checking out of enforce_node's recursive frame for the smaller Windows worker stack.
MARKTIP_NOINLINE void enforce_marks_uri(const Node& node, const Schema& schema, const UriPolicy& policy,
                                       PathStack& path) {
    bool extended = schema.has_declared_marks();
    // Frame order mirrors fill_node_from_py — marks, then content —
    // so the same violation reports the same .path whichever entry point built the tree.
    for (std::size_t i = 0; i < node.marks.size(); ++i) {
        if (node.marks[i].type == "link") {
            path.push_back({"marks", i});
            check_uri_attr(node.marks[i].attrs, "href", policy.link, [] { return std::string("link href"); }, path);
            path.pop_back();
        } else if (extended) {
            path.push_back({"marks", i});
            enforce_mark_uri(node.marks[i], schema, policy, path);
            path.pop_back();
        }
    }
}

void enforce_node(const Document& document, std::size_t index, const UriPolicy& policy, PathStack& path) {
    const Node& node = document.node(index);

    if (node.type == "image") {
        check_uri_attr(node.attrs, "src", policy.image, [] { return std::string("image src"); }, path);
    }
    if (!node.marks.empty()) {
        enforce_marks_uri(node, document.schema(), policy, path);
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

}  // namespace

RelativePolicy relative_policy_from_string(std::string_view value, const char* arg_name) {
    if (value == "allow") {
        return RelativePolicy::Allow;
    }
    if (value == "path_only") {
        return RelativePolicy::PathOnly;
    }
    if (value == "reject") {
        return RelativePolicy::Reject;
    }
    throw std::invalid_argument(std::string(arg_name) + " must be 'allow', 'path_only' or 'reject', not '" +
                                std::string(value) + "'");
}

void add_uri_scheme(UriRule& rule, std::string scheme, const char* arg_name) {
    scheme = ascii_lower(scheme);
    if (!is_valid_scheme(scheme)) {
        throw std::invalid_argument(std::string(arg_name) + " entry '" + scheme +
                                    "' is not a scheme name (expected e.g. 'https', not 'https://')");
    }
    auto position = std::lower_bound(rule.schemes.begin(), rule.schemes.end(), scheme);
    if (position == rule.schemes.end() || *position != scheme) {
        rule.schemes.insert(position, std::move(scheme));
    }
}

void add_rejected_node_type(NodeTypePolicy& policy, std::string type, const Schema& schema, const char* arg_name) {
    if (schema.node(type) == nullptr) {
        throw std::invalid_argument(std::string(arg_name) + " entry '" + type + "' is not a known node type");
    }
    auto position = std::lower_bound(policy.rejected.begin(), policy.rejected.end(), type);
    if (position == policy.rejected.end() || *position != type) {
        policy.rejected.insert(position, std::move(type));
    }
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

}  // namespace marktip
