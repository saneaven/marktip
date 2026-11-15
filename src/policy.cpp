#include "policy.h"

#include "ast.h"
#include "compiler.h"
#include "errors.h"
#include "entities.h"
#include "path.h"
#include "schema.h"

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
// The check resolves entity references itself (decode_entities).
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

template <typename DescribeOwner>
void enforce_declared_uri(const std::vector<AttrSpec>& specs, const AttrList& attrs,
                          const DescribeOwner& describe_owner, const UriPolicy& policy, const PathStack& path,
                          bool overlays_only) {
    for (const AttrSpec& attr : specs) {
        if (attr.uri == UriKind::None || (overlays_only && attr.form != MarkdownForm::Tag)) {
            continue;
        }
        const UriRule& rule = attr.uri == UriKind::Link ? policy.link : policy.image;
        auto describe = [&]() { return describe_owner() + " attr '" + attr.name + "'"; };
        check_uri_attr(attrs, attr.name.c_str(), rule, describe, path, true);
    }
}

void enforce_mark_uri(const Mark& mark, const Schema& schema, const UriPolicy& policy, const PathStack& path) {
    const MarkSpec& spec = *schema.mark(mark.type);
    auto describe_owner = [&]() { return "mark type '" + mark.type + "'"; };
    enforce_declared_uri(spec.attrs, mark.attrs, describe_owner, policy, path, spec.core);
}

void enforce_declared_node_uri(const Node& node, const Schema& schema, const UriPolicy& policy,
                               const PathStack& path) {
    const NodeSpec& spec = *schema.node(node.type);
    if (spec.core && spec.tag.empty()) {
        return;
    }
    auto describe_owner = [&]() { return "node type '" + node.type + "'"; };
    enforce_declared_uri(spec.attrs, node.attrs, describe_owner, policy, path, spec.core);
}

// Keep node/mark URI checking out of enforce_node's recursive frame for the smaller Windows worker stack.
MARKTIP_NOINLINE void enforce_fields_uri(const Node& node, const Schema& schema, const UriPolicy& policy,
                                        PathStack& path) {
    if (schema.has_declared_nodes() || schema.has_core_attrs()) {
        enforce_declared_node_uri(node, schema, policy, path);
    }
    bool extended = schema.has_declared_marks();
    // Frame order mirrors fill_node_from_py — marks, then content —
    // so the same violation reports the same .path whichever entry point built the tree.
    for (std::size_t i = 0; i < node.marks.size(); ++i) {
        if (node.marks[i].type == "link") {
            path.push_back({"marks", i});
            check_uri_attr(node.marks[i].attrs, "href", policy.link, [] { return std::string("link href"); }, path,
                           schema.has_link_tag());
            if (schema.has_link_uri()) {
                enforce_mark_uri(node.marks[i], schema, policy, path);
            }
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
        check_uri_attr(node.attrs, "src", policy.image, [] { return std::string("image src"); }, path,
                       document.schema().has_core_attrs() && !document.schema().node("image")->tag.empty());
    }
    if (!node.marks.empty() || document.schema().has_declared_nodes() || document.schema().has_core_attrs()) {
        enforce_fields_uri(node, document.schema(), policy, path);
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

void finalize_document(Document& document, const NodeTypePolicy& node_policy, const UriPolicy& uri_policy) {
    enforce_node_type_policy(document, node_policy);
    enforce_uri_policy(document, uri_policy);
    // URI errors must retain the input mark indices, so marks are ordered after policy checks.
    if (document.schema().has_declared_marks() || document.schema().has_core_attrs()) {
        document.order_marks();
    }
}

}  // namespace marktip
