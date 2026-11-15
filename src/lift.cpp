#include "lift.h"

#include <algorithm>
#include <charconv>
#include <limits>
#include <string>
#include <utility>
#include <vector>

#include "ast.h"
#include "compiler.h"
#include "entities.h"
#include "errors.h"
#include "form.h"
#include "path.h"
#include "schema.h"
#include "tags.h"
#include "validate.h"

namespace marktip {
namespace {

AttrInput decode_attr_input(const HtmlAttr& attr, const AttrSpec& spec) {
    if (!attr.value) {
        return spec.rule == AttrRule::Bool ? AttrInput(true) : AttrInput(OtherValue {});
    }
    std::string value = decode_entities(*attr.value);
    if (spec.rule == AttrRule::Str || spec.rule == AttrRule::Align) {
        return value;
    }
    if (spec.rule == AttrRule::Bool) {
        if (value == "true") {
            return true;
        }
        if (value == "false") {
            return false;
        }
        return OtherValue {};
    }
    if (spec.rule == AttrRule::ColWidth) {
        std::optional<std::vector<long long>> numbers = parse_int_list(value);
        return numbers ? AttrInput(std::move(*numbers)) : AttrInput(OtherValue {});
    }

    std::string_view digits = value;
    if (!digits.empty() && digits.front() == '+') {
        digits.remove_prefix(1);
        if (digits.empty() || !(digits.front() >= '0' && digits.front() <= '9')) {
            return OtherValue {};
        }
    }
    long long number;
    auto result = std::from_chars(digits.data(), digits.data() + digits.size(), number);
    if (result.ec != std::errc {} || result.ptr != digits.data() + digits.size()) {
        return OtherValue {};
    }
    return number;
}

AttrList decode_tag_attrs(const HtmlConstruct& tag, const std::vector<AttrSpec>& specs,
                          std::string_view type, const char* kind, const PathStack& path) {
    AttrList attrs;
    std::vector<std::string_view> seen;
    for (const HtmlAttr& attr : tag.attrs) {
        std::string name(attr.name);
        const AttrSpec& attr_spec = *check_attr_name(specs, name, false, type, kind,
                                                    StrictMode::Content, path, true);
        if (std::find(seen.begin(), seen.end(), attr.name) != seen.end()) {
            throw InvalidNodeError("invalid_attr_value", name, "attr '" + name + "' is repeated", format_path(path));
        }
        seen.push_back(attr.name);
        AttrInput input = decode_attr_input(attr, attr_spec);
        check_attr_value(input, attr_spec, path);
        AttrValue value;
        if (std::holds_alternative<std::string>(input)) {
            value = AttrValue::string(std::get<std::string>(std::move(input)));
        } else if (std::holds_alternative<long long>(input)) {
            value = AttrValue::integer(std::get<long long>(input));
        } else if (std::holds_alternative<bool>(input)) {
            value = AttrValue::boolean(std::get<bool>(input));
        } else {
            value = AttrValue::int_list(std::get<std::vector<long long>>(std::move(input)));
        }
        store_attr(attrs, std::move(name), std::move(value), specs);
    }
    if (type == "image" || type == "link") {
        attrs.erase(std::remove_if(attrs.begin(), attrs.end(), [](const auto& attr) {
            return attr.first == "title" && attr.second.string_value.empty();
        }), attrs.end());
        if (type == "image" && find_attr(attrs, "alt") == nullptr) {
            set_attr(attrs, "alt", AttrValue::string(""));
        }
    }
    check_required_attrs(attrs, specs, type, kind, path);
    AttrList ordered_attrs;
    for (const AttrSpec& attr_spec : specs) {
        auto attr = std::find_if(attrs.begin(), attrs.end(), [&](const auto& entry) {
            return entry.first == attr_spec.name;
        });
        if (attr != attrs.end()) {
            ordered_attrs.push_back(std::move(*attr));
        }
    }
    return ordered_attrs;
}

AttrList carrier_attrs(std::string body, const NodeSpec& spec, const PathStack& path) {
    const AttrSpec& body_spec = spec.attrs[spec.body];
    AttrInput input(std::move(body));
    check_attr_value(input, body_spec, path);
    AttrList attrs;
    store_attr(attrs, std::string(body_spec.name), AttrValue::string(std::get<std::string>(std::move(input))),
               spec.attrs);
    check_required_attrs(attrs, spec.attrs, spec.name, "node", path);
    return attrs;
}

struct OpenMark {
    const MarkSpec* spec;
    Mark mark;
};

enum class InlinePieceKind { Node, Atom, OpenContainer, CloseContainer };

struct InlinePiece {
    InlinePieceKind kind;
    std::size_t node;
    const NodeSpec* spec;
    std::optional<std::size_t> opening = std::nullopt;
};

struct PlacedChild {
    const NodeSpec* spec;
    std::size_t position;
};

struct InlineParent {
    std::size_t node;
    const NodeSpec* spec;
    std::vector<std::size_t> content;
    std::vector<PlacedChild> placed = {};
    std::optional<std::size_t> opening = std::nullopt;
};

[[noreturn]] void invalid_tag(std::string message, const PathStack& path) {
    throw InvalidNodeError("invalid_tag", "content", std::move(message), format_path(path));
}

void apply_declared_marks(std::vector<Mark>& marks, const std::vector<Mark>& effective,
                           const Schema& schema, const PathStack& path) {
    for (const Mark& mark : effective) {
        check_mark_set(marks, mark, schema, path);
    }
    marks.reserve(marks.size() + effective.size());
    for (const Mark& mark : effective) {
        marks.push_back(mark);
    }
}

void append_inline(Document& document, std::vector<std::size_t>& content, std::size_t index) {
    const Node& node = document.node(index);
    if (!content.empty() && (node.type == "text" || node.type == "htmlInline")) {
        Node& previous = document.node(content.back());
        if (previous.type == node.type && previous.marks == node.marks) {
            if (node.type == "text") {
                previous.text += node.text;
            } else {
                std::string html = attr_string(previous.attrs, "html");
                html += attr_string(node.attrs, "html");
                set_attr(previous.attrs, "html", AttrValue::string(std::move(html)));
            }
            return;
        }
    }
    content.push_back(index);
}

void append_raw(Document& document, std::vector<InlinePiece>& pieces, std::string value,
                 const std::vector<Mark>& core, const std::vector<Mark>& effective, bool html,
                 const PathStack& path) {
    if (value.empty()) {
        return;
    }
    Node node {html ? "htmlInline" : "text", {}, {}, core, {}};
    if (html) {
        set_attr(node.attrs, "html", AttrValue::string(std::move(value)));
    } else {
        node.text = std::move(value);
    }
    apply_declared_marks(node.marks, effective, document.schema(), path);
    std::size_t index = document.append_node(std::move(node));
    pieces.push_back({InlinePieceKind::Node, index, nullptr});
}

void check_lift_depth(std::size_t depth) {
    if (depth > kMaxNodeDepth) {
        throw ParseError("markdown_max_depth", "markdown nesting exceeds maximum depth");
    }
}

void complete_content(Document& document, std::size_t index, const NodeSpec& spec, PathStack& path);

void build_containers(Document& document, std::size_t index, const NodeSpec& parent_spec,
                       const std::vector<InlinePiece>& pieces, std::vector<std::size_t> content,
                       PathStack& path);

bool html_whitespace(std::string_view value) {
    return std::all_of(value.begin(), value.end(), [](char ch) {
        return ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n' || ch == '\v' || ch == '\f';
    });
}

bool single_tag(std::string_view payload, HtmlConstruct& tag) {
    bool found = false;
    for (const HtmlConstruct& token : tokenize_html(payload)) {
        if (token.name.empty() && html_whitespace(token.raw)) {
            continue;
        }
        if (found || token.name.empty()) {
            return false;
        }
        tag = token;
        found = true;
    }
    return found;
}

bool block_token(const Document& document, std::size_t index, std::string& payload, HtmlConstruct& token) {
    const Node& node = document.node(index);
    if (node.type == "htmlBlock") {
        payload = attr_string(node.attrs, "html");
    } else if (node.type == "paragraph") {
        for (std::size_t child : node.content) {
            const Node& part = document.node(child);
            if (part.type == "htmlInline") {
                payload += attr_string(part.attrs, "html");
            } else if (part.type == "text" && html_whitespace(part.text)) {
                payload += part.text;
            } else {
                return false;
            }
        }
    } else {
        return false;
    }
    return single_tag(payload, token);
}

AttrList decode_opening(const Document& document, std::size_t opening, const NodeSpec& spec,
                        const PathStack& path) {
    std::string payload;
    HtmlConstruct token;
    block_token(document, opening, payload, token);
    return decode_tag_attrs(token, spec.attrs, spec.name, "node", path);
}

// Block carriers are siblings before they are containers, so pair them before descending into their children.
MARKTIP_NOINLINE void process_blocks(Document& document, std::size_t index, const NodeSpec& parent_spec,
                                     PathStack& path, std::size_t& paired_from) {
    std::vector<std::size_t> original = std::move(document.node(index).content);
    std::vector<InlinePiece> pieces;
    pieces.reserve(original.size());
    const Schema& schema = document.schema();
    bool fences = schema.has_fences();
    const NodeSpec* display_math = schema.display_math();
    for (std::size_t child : original) {
        Node& parsed = document.node(child);
        const NodeSpec* carrier = nullptr;
        std::string body;
        if (fences && parsed.type == "codeBlock") {
            CodeInfo info = code_info(parsed.attrs);
            carrier = schema.fence(info.word);
            if (carrier != nullptr) {
                for (std::size_t line : parsed.content) {
                    body += document.node(line).text;
                }
                if (!body.empty() && body.back() == '\n') {
                    body.pop_back();
                }
            }
        } else if (display_math != nullptr && parsed.type == "paragraph" && parsed.content.size() == 1) {
            const Node& span = document.node(parsed.content.front());
            if (span.type == display_math->name) {
                carrier = display_math;
                body = attr_string(span.attrs, carrier->attrs[carrier->body].name);
                constexpr const char* whitespace = " \t\r\n\f\v";
                std::size_t begin = body.find_first_not_of(whitespace);
                if (begin == std::string::npos) {
                    body.clear();
                } else {
                    std::size_t end = body.find_last_not_of(whitespace);
                    body = body.substr(begin, end - begin + 1);
                }
            }
        }
        if (carrier != nullptr) {
            parsed.type = carrier->name;
            parsed.attrs = carrier_attrs(std::move(body), *carrier, path);
            parsed.content.clear();
            pieces.push_back({InlinePieceKind::Atom, child, carrier});
            continue;
        }
        std::string payload;
        HtmlConstruct token;
        const TagEntry* tag = nullptr;
        if (block_token(document, child, payload, token)) {
            tag = document.schema().tag(token.name);
        }
        if (tag == nullptr || tag->is_mark || !tag->block_line) {
            pieces.push_back({InlinePieceKind::Node, child, nullptr});
            continue;
        }

        const NodeSpec& spec = document.schema().node(tag->spec);
        if (token.closing) {
            if (token.self_closing || spec.shape == Shape::BlockAtom) {
                invalid_tag("closing tag '</" + spec.tag + ">' has no matching opening container", path);
            }
            pieces.push_back({InlinePieceKind::CloseContainer, 0, &spec});
            continue;
        }
        if (spec.shape == Shape::BlockContainer && token.self_closing) {
            invalid_tag("container tag '<" + spec.tag + "/>' must not be self-closing", path);
        }

        Node node;
        node.type = spec.name;
        // A UL's children decide whether it uses the task spec.
        bool list_owner = spec.core && (spec.tag == "ul" || spec.tag == "li");
        if (spec.core && spec.tag == "li" &&
            std::any_of(token.attrs.begin(), token.attrs.end(), [](const HtmlAttr& attr) {
                return attr.name == "checked";
            })) {
            node.type = "taskItem";
        }
        if (!list_owner) {
            node.attrs = decode_tag_attrs(token, spec.attrs, spec.name, "node", path);
        }
        std::size_t node_index = document.append_node(std::move(node));
        if (spec.core && spec.shape == Shape::BlockContainer) {
            paired_from = std::min(paired_from, node_index);
        }
        InlinePieceKind kind = spec.shape == Shape::BlockAtom ? InlinePieceKind::Atom
                                                              : InlinePieceKind::OpenContainer;
        pieces.push_back({kind, node_index, &spec, spec.core ? std::optional<std::size_t>(child) : std::nullopt});
    }
    build_containers(document, index, parent_spec, pieces, std::move(original), path);
}

const NodeSpec& peel_textblock(Document& document, std::size_t index, const NodeSpec& parent_spec,
                               const PathStack& path) {
    const std::vector<std::size_t>& content = document.node(index).content;
    if (parent_spec.name != "paragraph" || content.empty() ||
        document.node(content.front()).type != "htmlInline" ||
        document.node(content.back()).type != "htmlInline") {
        return parent_spec;
    }
    std::size_t first = content.front();
    std::size_t last = content.back();
    std::string first_payload = attr_string(document.node(first).attrs, "html");
    std::string last_payload = first == last ? first_payload : attr_string(document.node(last).attrs, "html");
    std::vector<HtmlConstruct> first_tokens = tokenize_html(first_payload);
    std::vector<HtmlConstruct> last_tokens = tokenize_html(last_payload);
    if (first_tokens.empty() || last_tokens.empty()) {
        return parent_spec;
    }
    const HtmlConstruct& opening = first_tokens.front();
    const HtmlConstruct& closing = last_tokens.back();
    const TagEntry* tag = document.schema().tag(opening.name);
    if (tag == nullptr || tag->is_mark || document.schema().node(tag->spec).shape != Shape::TextBlock ||
        opening.closing || opening.self_closing || !closing.closing || closing.self_closing ||
        closing.name != opening.name || opening.raw.data() != first_payload.data() ||
        closing.raw.data() + closing.raw.size() != last_payload.data() + last_payload.size()) {
        return parent_spec;
    }
    const NodeSpec& spec = document.schema().node(tag->spec);
    AttrList attrs = decode_tag_attrs(opening, spec.attrs, spec.name, "node", path);
    if (spec.name == "heading") {
        set_attr(attrs, "level", AttrValue::integer(opening.name[1] - '0'));
    }
    document.node(index).type = spec.name;
    document.node(index).attrs = std::move(attrs);
    if (first == last) {
        std::size_t length = first_payload.size() - opening.raw.size() - closing.raw.size();
        set_attr(document.node(first).attrs, "html",
                 AttrValue::string(first_payload.substr(opening.raw.size(), length)));
    } else {
        set_attr(document.node(first).attrs, "html", AttrValue::string(first_payload.substr(opening.raw.size())));
        set_attr(document.node(last).attrs, "html",
                 AttrValue::string(last_payload.substr(0, last_payload.size() - closing.raw.size())));
    }
    return spec;
}

void finish_parent(Document& document, InlineParent& parent, PathStack& path, std::size_t source_depth) {
    document.node(parent.node).content = std::move(parent.content);
    const Schema& schema = document.schema();
    if (schema.has_list_tags() && document.node(parent.node).type == "bulletList") {
        normalize_task_list(document, parent.node);
        parent.spec = schema.node(document.node(parent.node).type);
    }
    if (parent.opening && parent.spec->core &&
        (parent.spec->tag == "ul" || parent.spec->tag == "li")) {
        // Deferred UL attrs retain the tag's original parent path after list normalization.
        PathStack attr_path(path.begin(), path.begin() + source_depth);
        const NodeSpec& spec = *schema.node(document.node(parent.node).type);
        parent.spec = &spec;
        Node& node = document.node(parent.node);
        node.attrs = decode_opening(document, *parent.opening, spec, attr_path);
    }
    if (!parent.spec->core && parent.spec->shape == Shape::InlineContainer) {
        complete_content(document, parent.node, *parent.spec, path);
    }
    std::size_t siblings = document.node(parent.node).content.size();
    if (siblings != 0) {
        check_lift_depth(path.size() + 1);
    }
    if (parent.opening && parent.spec->core) {
        check_node_content(document, parent.node, *parent.spec, path);
        return;
    }
    for (const PlacedChild& child : parent.placed) {
        path.push_back({"content", child.position});
        std::size_t index = document.node(parent.node).content[child.position];
        check_child_content(document, *parent.spec, *child.spec, document.node(index), siblings, path);
        path.pop_back();
    }
}

void build_containers(Document& document, std::size_t index, const NodeSpec& parent_spec,
                       const std::vector<InlinePiece>& pieces, std::vector<std::size_t> content,
                       PathStack& path) {
    // Reuse the parsed child storage instead of allocating another list for the inline parent.
    content.clear();
    InlineParent current {index, &parent_spec, std::move(content)};
    std::vector<InlineParent> parents;
    std::size_t parent_depth = path.size();
    for (const InlinePiece& piece : pieces) {
        if (piece.kind == InlinePieceKind::CloseContainer) {
            if (parents.empty() || current.spec != piece.spec) {
                path.resize(parent_depth);
                invalid_tag("closing tag '</" + piece.spec->tag + ">' has no matching opening container", path);
            }
            std::size_t node = current.node;
            finish_parent(document, current, path, parent_depth);
            const NodeSpec* spec = current.spec;
            current = std::move(parents.back());
            parents.pop_back();
            if (current.spec->dfa < 0) {
                current.placed.push_back({spec, current.content.size()});
            }
            append_inline(document, current.content, node);
            path.pop_back();
            continue;
        }

        if (piece.kind == InlinePieceKind::OpenContainer) {
            path.push_back({"content", current.content.size()});
            check_lift_depth(path.size());
            parents.push_back(std::move(current));
            current = {piece.node, piece.spec, {}};
            current.opening = piece.opening;
            continue;
        }
        if (piece.kind == InlinePieceKind::Atom) {
            if (!parents.empty()) {
                check_lift_depth(path.size() + 1);
            }
            if (current.spec->dfa < 0) {
                current.placed.push_back({piece.spec, current.content.size()});
            }
        } else if (!parents.empty()) {
            check_lift_depth(path.size() + 1);
        }
        append_inline(document, current.content, piece.node);
    }
    if (!parents.empty()) {
        const NodeSpec& opening = *(parents.size() == 1 ? current.spec : parents[1].spec);
        path.resize(parent_depth);
        invalid_tag("opening tag '<" + opening.tag + ">' has no matching closing container", path);
    }
    finish_parent(document, current, path, parent_depth);
}

// Clang otherwise inlines this state into lift_node, exhausting small worker stacks on deep documents.
MARKTIP_NOINLINE const NodeSpec& process_inline(Document& document, std::size_t index, const NodeSpec& parent_spec,
                                               bool html, PathStack& path) {
    const Schema& schema = document.schema();
    const NodeSpec& content_spec = schema.has_declared_nodes() || schema.has_core_attrs()
                                      ? peel_textblock(document, index, parent_spec, path)
                                      : parent_spec;
    std::vector<std::size_t> original = std::move(document.node(index).content);
    std::vector<InlinePiece> pieces;
    pieces.reserve(original.size());
    std::vector<OpenMark> open;
    std::vector<Mark> effective;
    bool math = schema.has_math();
    const NodeSpec* inline_math = math ? schema.inline_math() : nullptr;
    const NodeSpec* display_math = math ? schema.display_math() : nullptr;
    for (std::size_t child : original) {
        if (document.node(child).type != "htmlInline") {
            Node& node = document.node(child);
            const NodeSpec* carrier = nullptr;
            if (math) {
                if (inline_math != nullptr && node.type == inline_math->name) {
                    carrier = inline_math;
                    node.attrs = carrier_attrs(attr_string(node.attrs, carrier->attrs[carrier->body].name),
                                               *carrier, path);
                } else if (display_math != nullptr && node.type == display_math->name) {
                    node.text = "$$" + attr_string(node.attrs, display_math->attrs[display_math->body].name) + "$$";
                    node.type = "text";
                    node.attrs.clear();
                }
            }
            apply_declared_marks(node.marks, effective, schema, path);
            pieces.push_back({carrier != nullptr ? InlinePieceKind::Atom : InlinePieceKind::Node, child, carrier});
            continue;
        }

        std::string payload = attr_string(document.node(child).attrs, "html");
        std::vector<Mark> core = document.node(child).marks;
        std::string raw;
        for (const HtmlConstruct& token : tokenize_html(payload)) {
            const TagEntry* tag = schema.tag(token.name);
            if (tag == nullptr) {
                raw.append(token.raw.data(), token.raw.size());
                continue;
            }
            append_raw(document, pieces, std::move(raw), core, effective, html, path);
            raw.clear();

            if (!tag->is_mark) {
                const NodeSpec& spec = schema.node(tag->spec);
                if (spec.shape != Shape::InlineAtom && spec.shape != Shape::InlineContainer) {
                    invalid_tag("tag '<" + std::string(token.name) + ">' must occupy its declared block form", path);
                }
                if (spec.shape == Shape::InlineContainer && token.closing && !token.self_closing) {
                    pieces.push_back({InlinePieceKind::CloseContainer, 0, &spec});
                    continue;
                }
                if (token.closing || (spec.shape == Shape::InlineContainer && token.self_closing)) {
                    invalid_tag("invalid carrier tag for node type '" + spec.name + "'", path);
                }
                Node node;
                node.type = spec.name;
                node.attrs = decode_tag_attrs(token, spec.attrs, spec.name, "node", path);
                InlinePieceKind kind = InlinePieceKind::OpenContainer;
                if (spec.shape == Shape::InlineAtom) {
                    node.marks = core;
                    apply_declared_marks(node.marks, effective, schema, path);
                    kind = InlinePieceKind::Atom;
                }
                std::size_t node_index = document.append_node(std::move(node));
                pieces.push_back({kind, node_index, &spec});
                continue;
            }

            const MarkSpec& spec = schema.mark(tag->spec);
            if (token.self_closing) {
                invalid_tag("mark tag '<" + std::string(token.closing ? "/" : "") +
                                std::string(token.name) + "/>' must not be self-closing", path);
            }
            if (!token.closing) {
                check_lift_depth(open.size() + 1);
                Mark mark {spec.name, decode_tag_attrs(token, spec.attrs, spec.name, "mark", path)};
                if (excludes(spec.excludes, spec.name)) {
                    auto previous = std::find_if(effective.begin(), effective.end(), [&](const Mark& current) {
                        return current.type == spec.name;
                    });
                    if (previous != effective.end()) {
                        effective.erase(previous);
                    }
                }
                check_mark_set(effective, mark, schema, path);
                effective.push_back(mark);
                order_marks(effective, schema);
                open.push_back({&spec, std::move(mark)});
                continue;
            }

            // Marks form a flat set, so other types may cross this type's closing boundary.
            auto opening = std::find_if(open.rbegin(), open.rend(), [&](const OpenMark& mark) {
                return mark.spec == &spec;
            });
            if (opening == open.rend()) {
                invalid_tag("closing tag '</" + std::string(token.name) + ">' has no matching opening tag", path);
            }
            // Equal-type order follows opening order, so the last mark of this type is the one closing.
            auto active = std::find_if(effective.rbegin(), effective.rend(), [&](const Mark& mark) {
                return mark.type == spec.name;
            });
            effective.erase(active.base() - 1);
            open.erase(opening.base() - 1);
            if (excludes(spec.excludes, spec.name)) {
                auto outer = std::find_if(open.rbegin(), open.rend(), [&](const OpenMark& mark) {
                    return mark.spec == &spec;
                });
                if (outer != open.rend()) {
                    effective.push_back(outer->mark);
                    order_marks(effective, schema);
                }
            }
        }
        append_raw(document, pieces, std::move(raw), core, effective, html, path);
    }
    if (!open.empty()) {
        invalid_tag("opening tag '<" + open.front().spec->tag + ">' has no matching closing tag", path);
    }
    // Mark pairs are resolved over the flat sequence before containers add structure.
    // Heap-backed parent frames also let excessive tag nesting fail before recursive traversal.
    build_containers(document, index, content_spec, pieces, std::move(original), path);
    return content_spec;
}

const NodeSpec& lift_node(Document& document, std::size_t index, bool html, bool block_forms, PathStack& path,
                          std::size_t& paired_from) {
    if (block_forms) {
        check_lift_depth(path.size());
    }
    const NodeSpec& spec = *document.schema().node(document.node(index).type);
    if (spec.allow == ContentModel::Inlines) {
        return process_inline(document, index, spec, html, path);
    }
    // Appended core containers were paired already; parser-built nodes have lower arena indices.
    if (block_forms && spec.core && spec.allow == ContentModel::Blocks && index < paired_from) {
        process_blocks(document, index, spec, path, paired_from);
    }
    for (std::size_t i = 0; i < document.node(index).content.size(); ++i) {
        path.push_back({"content", i});
        std::size_t child = document.node(index).content[i];
        const NodeSpec& child_spec = lift_node(document, child, html, block_forms, path, paired_from);
        if (child_spec.shape == Shape::TextBlock) {
            check_child_content(document, spec, child_spec, document.node(child),
                                document.node(index).content.size(), path);
            complete_content(document, child, child_spec, path);
        }
        path.pop_back();
    }
    if (!spec.core) {
        complete_content(document, index, spec, path);
    }
    return spec;
}

struct CreationFrame {
    std::size_t node;
    const std::vector<std::string>* children;
    std::size_t next;
    std::size_t depth;
};

std::size_t create_minimal_node(Document& document, const NodeSpec& spec, std::size_t depth) {
    check_lift_depth(depth);
    const Schema& schema = document.schema();
    std::size_t root = document.append_node(Node {spec.name, {}, {}, {}, {}});
    std::vector<CreationFrame> frames;
    frames.push_back({root, schema.minimum_content(spec), 0, depth});
    while (!frames.empty()) {
        CreationFrame& frame = frames.back();
        if (frame.next == frame.children->size()) {
            frames.pop_back();
            continue;
        }
        const NodeSpec& child_spec = *schema.node((*frame.children)[frame.next++]);
        std::size_t child_depth = frame.depth + 1;
        check_lift_depth(child_depth);
        std::size_t child = document.append_child(frame.node, Node {child_spec.name, {}, {}, {}, {}});
        frames.push_back({child, schema.minimum_content(child_spec), 0, child_depth});
    }
    return root;
}

struct DepthFrame {
    std::size_t node;
    std::size_t depth;
};

void check_wrapped_depth(const Document& document, const std::vector<std::size_t>& children,
                          std::size_t begin, std::size_t end, std::size_t depth) {
    std::vector<DepthFrame> pending;
    for (std::size_t i = begin; i < end; ++i) {
        pending.push_back({children[i], depth});
    }
    while (!pending.empty()) {
        DepthFrame frame = pending.back();
        pending.pop_back();
        check_lift_depth(frame.depth);
        for (std::size_t child : document.node(frame.node).content) {
            pending.push_back({child, frame.depth + 1});
        }
    }
}

void wrap_implicit_children(Document& document, std::size_t index, const ContentDFA& content,
                              const PathStack& path, std::vector<std::size_t>& created) {
    for (const std::string& type : content.implicit_types) {
        const NodeSpec& spec = *document.schema().node(type);
        const ContentDFA& wrapper = document.schema().content(spec.dfa);
        std::vector<std::size_t> original = std::move(document.node(index).content);
        std::vector<std::size_t> children;
        children.reserve(original.size());
        bool wrapped = false;
        for (std::size_t i = 0; i < original.size();) {
            if (wrapped || !wrapper.accepts_type(document.node(original[i]).type)) {
                children.push_back(original[i++]);
                continue;
            }
            std::size_t end = i + 1;
            while (end < original.size() && wrapper.accepts_type(document.node(original[end]).type)) {
                ++end;
            }
            check_lift_depth(path.size() + 1);
            check_wrapped_depth(document, original, i, end, path.size() + 2);
            Node node;
            node.type = spec.name;
            node.content.assign(original.begin() + i, original.begin() + end);
            std::size_t wrapper_index = document.append_node(std::move(node));
            children.push_back(wrapper_index);
            created.push_back(wrapper_index);
            wrapped = true;
            i = end;
        }
        document.node(index).content = std::move(children);
    }
}

void complete_one_content(Document& document, std::size_t index, const NodeSpec& spec, const PathStack& path,
                           std::vector<std::size_t>& created) {
    const Schema& schema = document.schema();
    const ContentDFA& content = schema.content(spec.dfa);
    wrap_implicit_children(document, index, content, path, created);
    std::vector<std::string_view> types;
    types.reserve(document.node(index).content.size());
    for (std::size_t child : document.node(index).content) {
        types.push_back(document.node(child).type);
    }
    if (content.match(types)) {
        return;
    }
    std::optional<std::vector<ContentFill>> filled = content.fill(types, schema.creatable_types());
    if (!filled) {
        check_node_content(document, index, spec, path);
    } else {
        std::vector<std::size_t> original = std::move(document.node(index).content);
        std::vector<std::size_t> children;
        children.reserve(filled->size());
        for (const ContentFill& child : *filled) {
            if (child.original) {
                children.push_back(original[*child.original]);
            } else {
                children.push_back(create_minimal_node(document, *schema.node(child.type), path.size() + 1));
            }
        }
        document.node(index).content = std::move(children);
    }
}

struct CompletionFrame {
    std::size_t node;
    std::vector<std::size_t> created;
    std::size_t next;
};

void complete_content(Document& document, std::size_t index, const NodeSpec& spec, PathStack& path) {
    if (spec.dfa < 0) {
        return;
    }
    std::vector<std::size_t> created;
    complete_one_content(document, index, spec, path, created);
    if (created.empty()) {
        return;
    }
    std::vector<CompletionFrame> pending;
    pending.push_back({index, std::move(created), 0});
    while (!pending.empty()) {
        CompletionFrame& frame = pending.back();
        if (frame.next == frame.created.size()) {
            pending.pop_back();
            if (!pending.empty()) {
                path.pop_back();
            }
            continue;
        }
        std::size_t child = frame.created[frame.next++];
        const std::vector<std::size_t>& children = document.node(frame.node).content;
        std::size_t position = static_cast<std::size_t>(std::find(children.begin(), children.end(), child) -
                                                        children.begin());
        path.push_back({"content", position});
        const NodeSpec& child_spec = *document.schema().node(document.node(child).type);
        std::vector<std::size_t> nested;
        complete_one_content(document, child, child_spec, path, nested);
        if (nested.empty()) {
            path.pop_back();
        } else {
            pending.push_back({child, std::move(nested), 0});
        }
    }
}

}  // namespace

void lift(Document& document, bool html) {
    PathStack path;
    path.reserve(32);
    bool block_forms = std::any_of(document.schema().tags().begin(), document.schema().tags().end(),
                                    [](const TagEntry& tag) { return tag.block_line; });
    std::size_t paired_from = std::numeric_limits<std::size_t>::max();
    lift_node(document, 0, html, block_forms, path, paired_from);
}

}  // namespace marktip
