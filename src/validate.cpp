#include "validate.h"

#include <algorithm>
#include <stdexcept>
#include <utility>

#include "ast.h"
#include "errors.h"
#include "form.h"
#include "tags.h"

namespace marktip {
namespace {

bool equal_attrs(const AttrList& left, const AttrList& right) {
    return left.size() == right.size() && std::all_of(left.begin(), left.end(), [&](const auto& attr) {
        return std::any_of(right.begin(), right.end(), [&](const auto& other) {
            return attr.first == other.first && attr.second == other.second;
        });
    });
}

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

[[noreturn]] void throw_unknown_field(const std::string& name, std::string_view owner_type, const char* kind,
                                     const PathStack& path) {
    throw InvalidNodeError("unknown_field", name,
                           "field '" + name + "' is not defined for " + kind + " type '" +
                               std::string(owner_type) + "'",
                           format_path(path));
}

[[noreturn]] void throw_missing_attr(const AttrSpec& spec, std::string_view owner_type, const char* kind,
                                    const PathStack& path) {
    std::string name(spec.name);
    throw InvalidNodeError("missing_attr", name,
                           "attr '" + name + "' is required for " + kind + " type '" +
                               std::string(owner_type) + "'",
                           format_path(path));
}

[[noreturn]] void throw_invalid_child_content(const NodeSpec& parent, const NodeSpec& child,
                                             const PathStack& path) {
    throw InvalidNodeError("invalid_content", "content",
                           "node type '" + parent.name + "' cannot contain node type '" + child.name + "'",
                           format_path(path));
}

[[noreturn]] void throw_code_block_marks(const PathStack& path) {
    throw InvalidNodeError("invalid_content", "marks", "text inside codeBlock must not carry marks",
                           format_path(path));
}

[[noreturn]] void throw_declared_html(const PathStack& path) {
    throw InvalidNodeError("unrepresentable", "html",
                           "attr 'html' cannot be expressed in markdown: raw HTML is parsed as a declared tag",
                           format_path(path));
}

[[noreturn]] void throw_declared_fence(const char* field, const PathStack& path) {
    throw InvalidNodeError("unrepresentable", field,
                           "attr '" + std::string(field) +
                               "' cannot be expressed in markdown: code block is parsed as a declared node",
                           format_path(path));
}

[[noreturn]] void throw_atom_code_marks(const NodeSpec& spec, const PathStack& path) {
    throw InvalidNodeError("invalid_mark_set", "marks",
                           "node type '" + spec.name + "' must not carry a code mark", format_path(path));
}

[[noreturn]] void throw_declared_content(const NodeSpec& spec, const PathStack& path) {
    throw InvalidNodeError("invalid_content", "content",
                           "node type '" + spec.name + "' does not match its content expression", format_path(path));
}

[[noreturn]] void throw_table_container(const NodeSpec& spec, const PathStack& path) {
    throw InvalidNodeError("unrepresentable", "content",
                           "node type '" + spec.name + "' cannot be expressed in markdown inside a table cell",
                           format_path(path));
}

[[noreturn]] void throw_table_siblings(const NodeSpec& spec, const PathStack& path) {
    throw InvalidNodeError("unrepresentable", "content",
                           "node type '" + spec.name + "' must be the only child of a table cell",
                           format_path(path));
}

}  // namespace

void check_type_present(bool present, std::string_view context, const PathStack& path) {
    if (!present) {
        throw InvalidNodeError("missing_type", "type", std::string(context) + " is missing required key 'type'",
                               format_path(path));
    }
}

const NodeSpec* require_node_spec(const Schema& schema, std::string_view type, const PathStack& path) {
    const NodeSpec* spec = schema.node(type);
    if (spec == nullptr) {
        throw UnknownTypeError("node", std::string(type), format_path(path));
    }
    return spec;
}

const MarkSpec* require_mark_spec(const Schema& schema, std::string_view type, const PathStack& path) {
    const MarkSpec* spec = schema.mark(type);
    if (spec == nullptr) {
        throw UnknownTypeError("mark", std::string(type), format_path(path));
    }
    return spec;
}

void check_root_type(std::string_view type, const PathStack& path) {
    if (type != "doc") {
        throw InvalidNodeError("invalid_root", "type", "root node must have type 'doc'", format_path(path));
    }
}

void check_node_depth(std::size_t depth, const PathStack& path) {
    if (depth > kMaxNodeDepth) {
        throw InvalidNodeError("max_depth", "content", "node content nesting exceeds maximum depth",
                               format_path(path));
    }
}

void check_top_level_field(const std::string& name, std::string_view owner_type, const char* kind,
                           bool inline_type, const PathStack& path) {
    bool allowed = name == "type" || name == "attrs";
    if (std::string_view(kind) == "mark") {
        if (!allowed) {
            throw_unknown_field(name, owner_type, "mark", path);
        }
        return;
    }

    allowed = allowed || name == "content" || (name == "text" && owner_type == "text") ||
              (name == "marks" && inline_type);
    if (!allowed) {
        throw_unknown_field(name, owner_type, "node", path);
    }
}

bool node_allows_marks(const NodeSpec& spec) {
    return spec.core ? spec.is_inline : spec.shape == Shape::InlineAtom;
}

void check_text_payload(bool present, bool is_string, std::string_view value, const PathStack& path) {
    if (!present) {
        throw InvalidNodeError("invalid_content", "text", "text node is missing required field 'text'",
                               format_path(path));
    }
    if (!is_string) {
        throw InvalidNodeError("invalid_content", "text", "text node field 'text' must be a str", format_path(path));
    }
    if (value.empty()) {
        throw InvalidNodeError("invalid_content", "text", "text node field 'text' must not be empty",
                               format_path(path));
    }
}

void check_raw_carriers(const Node& node, const Schema& schema, const PathStack& path) {
    if (!schema.has_tags()) {
        return;
    }
    if (node.type == "codeBlock") {
        if (schema.has_fences()) {
            CodeInfo info = code_info(node.attrs);
            if (schema.fence(info.word) != nullptr) {
                throw_declared_fence(info.field, path);
            }
        }
        return;
    }
    if (node.type != "htmlInline" && node.type != "htmlBlock") {
        return;
    }
    std::string html = attr_string(node.attrs, "html");
    if (node.type == "htmlInline" ? contains_declared_tag(html, schema) : starts_declared_tag(html, schema)) {
        throw_declared_html(path);
    }
}

const AttrSpec* check_attr_name(const std::vector<AttrSpec>& specs, const std::string& name, bool is_none,
                                std::string_view owner_type, const char* kind, StrictMode mode,
                                const PathStack& path, bool tag_form) {
    const AttrSpec* spec = find_attr_spec(specs, name);
    if (spec == nullptr || (tag_form && spec->form == MarkdownForm::Dropped)) {
        // Outside both dialects: a typo, or a key an app invented and expects to survive.
        throw InvalidNodeError("unknown_attr", name,
                               "attr '" + name + "' is not defined for " + kind + " type '" +
                                   std::string(owner_type) + "'",
                               format_path(path));
    }
    // Unset rather than wrongly typed: this is what the editor submits for an attr nobody filled in,
    // so refusing it would refuse ordinary editor output.
    // A Refused attr still fails the value rule below —
    // Tiptap gives those a non-null default and never emits a null for one,
    // so a null there is a caller bug worth reporting even though the conversion survives it.
    if (spec->null == NullAttr::Unset && is_none) {
        return nullptr;
    }
    // Refused before the value is looked at: under Exact the name alone settles it,
    // and a caller who will not lose a width does not need to hear that this one is malformed too.
    if (spec->form == MarkdownForm::Dropped && mode == StrictMode::Exact) {
        throw InvalidNodeError("unrepresentable", name,
                               "attr '" + name + "' cannot be expressed in markdown: " + spec->why,
                               format_path(path));
    }
    return spec;
}

bool attr_reads_string(const AttrSpec& spec) {
    return spec.rule == AttrRule::InfoStr || spec.rule == AttrRule::Align ||
           (spec.rule == AttrRule::Str && spec.choices);
}

bool attr_reads_int_list(const AttrSpec& spec) {
    return spec.rule == AttrRule::ColWidth;
}

void check_attr_value(const AttrInput& value, const AttrSpec& spec, const PathStack& path) {
    auto expected = [&](const char* what) {
        throw InvalidNodeError("invalid_attr_value", spec.name, "attr '" + spec.name + "' must be " + what,
                               format_path(path));
    };
    auto unrepresentable = [&](const char* why) {
        throw InvalidNodeError("unrepresentable", spec.name,
                               "attr '" + spec.name + "' cannot be expressed in markdown: " + why, format_path(path));
    };

    const long long* number = std::get_if<long long>(&value);
    switch (spec.rule) {
        case AttrRule::Str:
            if (!std::holds_alternative<std::string>(value)) {
                expected("a str");
            }
            break;
        case AttrRule::InfoStr:
            if (!std::holds_alternative<std::string>(value)) {
                expected("a str");
            }
            if (std::get<std::string>(value).find_first_of("\r\n") != std::string::npos) {
                expected("a single line");
            }
            break;
        case AttrRule::Bool:
            if (!std::holds_alternative<bool>(value)) {
                expected("a bool");
            }
            break;
        case AttrRule::Int:
            if (number == nullptr) {
                expected("an int");
            }
            break;
        case AttrRule::Level:
            if (number == nullptr || *number < 1 || *number > 6) {
                expected("an int between 1 and 6");
            }
            break;
        case AttrRule::ListStart:
            if (number == nullptr || *number < 0 || *number > kMaxListStart) {
                expected("an int between 0 and 999999999");
            }
            break;
        case AttrRule::Count:
            if (number == nullptr || *number < 0) {
                expected("a non-negative int");
            }
            break;
        case AttrRule::Align:
            if (std::holds_alternative<std::monostate>(value)) {
                break;
            }
            if (!std::holds_alternative<std::string>(value)) {
                expected("'left', 'center', 'right' or None");
            }
            {
                const std::string& align = std::get<std::string>(value);
                if (align != "left" && align != "center" && align != "right") {
                    expected("'left', 'center', 'right' or None");
                }
            }
            break;
        case AttrRule::Size:
            if (!std::holds_alternative<std::string>(value) && number == nullptr &&
                !std::holds_alternative<OverflowInt>(value)) {
                expected("a str or an int");
            }
            break;
        case AttrRule::ColWidth:
            if (!std::holds_alternative<std::vector<long long>>(value)) {
                expected("a list of ints");
            }
            break;
        case AttrRule::NoSpan:
            if (number == nullptr) {
                expected("an int");
            }
            if (*number != 1) {
                unrepresentable("GFM tables have no cell spanning");
            }
            break;
    }

    if (spec.choices) {
        if (std::none_of(spec.choices->begin(), spec.choices->end(), [&](const AttrValue& choice) {
                if (choice.kind == AttrValue::Kind::String) {
                    return std::get<std::string>(value) == choice.string_value;
                }
                if (choice.kind == AttrValue::Kind::Int) {
                    return std::get<long long>(value) == choice.int_value;
                }
                if (choice.kind == AttrValue::Kind::IntList) {
                    return std::get<std::vector<long long>>(value) == choice.int_list_value();
                }
                return std::get<bool>(value) == choice.bool_value;
            })) {
            expected("one of the declared choices");
        }
    }
}

// Reads the built AttrList rather than the input dict,
// so "no such key" and "the key is None" arrive here as one case — attrs_from_py has already dropped the None.
// A node carrying no attrs dict at all is the third spelling,
// which is why the caller runs this outside its `attrs` block.
void check_required_attrs(const AttrList& attrs, const std::vector<AttrSpec>& specs,
                          std::string_view owner_type, const char* kind, const PathStack& path) {
    for (const AttrSpec& spec : specs) {
        if (spec.presence != Presence::Required || find_attr(attrs, spec.name) != nullptr) {
            continue;
        }
        throw_missing_attr(spec, owner_type, kind, path);
    }
}

void store_attr(AttrList& attrs, std::string&& name, AttrValue&& value, const std::vector<AttrSpec>& specs) {
    const AttrSpec* spec = find_attr_spec(specs, name);
    if (value.kind == AttrValue::Kind::IntList &&
        (spec == nullptr || spec->rule != AttrRule::ColWidth || spec->form == MarkdownForm::Dropped)) {
        return;
    }
    if (value.kind == AttrValue::Kind::String && (spec == nullptr || spec->uri == UriKind::None)) {
        value.string_value = normalize_content_string(std::move(value.string_value));
    }
    if (spec != nullptr && spec->fallback && value == *spec->fallback) {
        return;
    }
    set_attr(attrs, std::move(name), std::move(value));
}

void check_content_field(const NodeSpec& spec, const PathStack& path) {
    if (spec.allow == ContentModel::None && spec.dfa < 0) {
        throw InvalidNodeError("invalid_content", "content", "node type '" + spec.name + "' must not carry content",
                               format_path(path));
    }
}

void check_child_content(const Document& document, const NodeSpec& parent, const NodeSpec& child,
                         const Node& child_node, std::size_t siblings, const PathStack& path) {
    if (parent.dfa >= 0) {
        return;
    }
    if (!document.schema().content_model_allows(parent.allow, child)) {
        throw_invalid_child_content(parent, child, path);
    }
    if ((parent.name == "tableCell" || parent.name == "tableHeader") &&
        !document.schema().has_table_tags() && (!child.core || uses_tag_form(document, child_node, child))) {
        if (child.shape == Shape::BlockContainer) {
            throw_table_container(child, path);
        }
        if (siblings != 1) {
            throw_table_siblings(child, path);
        }
    }
    if (parent.allow == ContentModel::Text && !child_node.marks.empty()) {
        throw_code_block_marks(path);
    }
}

void check_node_marks(const Node& node, const NodeSpec& spec, const PathStack& path) {
    if (!spec.core && spec.shape == Shape::InlineAtom &&
        std::any_of(node.marks.begin(), node.marks.end(), [](const Mark& mark) { return mark.type == "code"; })) {
        throw_atom_code_marks(spec, path);
    }
}

// Keep the complete child sequence out of the recursive dict and lift frames.
void check_node_content(const Document& document, std::size_t index, const NodeSpec& spec, const PathStack& path) {
    if (spec.dfa < 0) {
        const Node& node = document.node(index);
        PathStack child_path = path;
        for (std::size_t position = 0; position < node.content.size(); ++position) {
            const Node& child = document.node(node.content[position]);
            child_path.push_back({"content", position});
            check_child_content(document, spec, *document.schema().node(child.type), child,
                                node.content.size(), child_path);
            child_path.pop_back();
        }
        return;
    }
    const Node& node = document.node(index);
    std::vector<std::string_view> children;
    children.reserve(node.content.size());
    for (std::size_t child : node.content) {
        children.push_back(document.node(child).type);
    }
    if (!document.schema().content(spec.dfa).match(children)) {
        throw_declared_content(spec, path);
    }
}

bool excludes(const ExcludeSet& set, std::string_view type) {
    return set.all || std::find(set.names.begin(), set.names.end(), type) != set.names.end();
}

void check_mark_set(const std::vector<Mark>& existing, const Mark& mark, const Schema& schema,
                    const PathStack& path) {
    if (existing.empty()) {
        return;
    }
    const MarkSpec& spec = *schema.mark(mark.type);
    for (const Mark& earlier : existing) {
        const MarkSpec& earlier_spec = *schema.mark(earlier.type);
        bool same_type = earlier.type == mark.type;
        if ((same_type && equal_attrs(earlier.attrs, mark.attrs)) || excludes(spec.excludes, earlier.type) ||
            excludes(earlier_spec.excludes, mark.type)) {
            std::string message = same_type
                                      ? "mark type '" + mark.type + "' conflicts with an earlier mark of the same type"
                                      : "mark type '" + mark.type +
                                            "' conflicts with earlier mark type '" + earlier.type + "'";
            throw InvalidNodeError("invalid_mark_set", "marks", std::move(message), format_path(path));
        }
    }
}

StrictMode strict_mode_from_string(std::string_view level, const char* arg_name) {
    if (level == "off") {
        return StrictMode::Off;
    }
    if (level == "content") {
        return StrictMode::Content;
    }
    if (level == "exact") {
        return StrictMode::Exact;
    }
    throw std::invalid_argument(std::string(arg_name) + " must be 'off', 'content' or 'exact', not '" +
                                std::string(level) + "'");
}

}  // namespace marktip
