#include "lift.h"

#include <algorithm>
#include <charconv>
#include <string>
#include <utility>
#include <vector>

#include "ast.h"
#include "compiler.h"
#include "entities.h"
#include "errors.h"
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
    if (spec.rule == AttrRule::Str) {
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
                                                    StrictMode::Content, path);
        if (std::find(seen.begin(), seen.end(), attr.name) != seen.end()) {
            throw InvalidNodeError("invalid_attr_value", name, "attr '" + name + "' is repeated", format_path(path));
        }
        seen.push_back(attr.name);
        AttrInput input = decode_attr_input(attr, attr_spec);
        check_attr_value(input, attr_spec, path);
        AttrValue value;
        if (attr_spec.rule == AttrRule::Str) {
            value = AttrValue::string(std::get<std::string>(std::move(input)));
        } else if (attr_spec.rule == AttrRule::Int) {
            value = AttrValue::integer(std::get<long long>(input));
        } else {
            value = AttrValue::boolean(std::get<bool>(input));
        }
        store_attr(attrs, std::move(name), std::move(value), specs);
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

struct OpenMark {
    const MarkSpec* spec;
    Mark mark;
};

enum class InlinePieceKind { Node, Atom, OpenContainer, CloseContainer };

struct InlinePiece {
    InlinePieceKind kind;
    std::size_t node;
    const NodeSpec* spec;
};

struct InlineParent {
    std::size_t node;
    const NodeSpec* spec;
    std::vector<std::size_t> content;
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
            document.node(node).content = std::move(current.content);
            check_node_content(document, node, *piece.spec, path);
            current = std::move(parents.back());
            parents.pop_back();
            check_child_content(document.schema(), *current.spec, *piece.spec, document.node(node), path);
            append_inline(document, current.content, node);
            path.pop_back();
            continue;
        }

        if (piece.kind == InlinePieceKind::OpenContainer) {
            path.push_back({"content", current.content.size()});
            check_lift_depth(path.size());
            parents.push_back(std::move(current));
            current = {piece.node, piece.spec, {}};
            continue;
        }
        if (piece.kind == InlinePieceKind::Atom) {
            path.push_back({"content", current.content.size()});
            if (!parents.empty()) {
                check_lift_depth(path.size());
            }
            check_child_content(document.schema(), *current.spec, *piece.spec, document.node(piece.node), path);
            path.pop_back();
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
    document.node(index).content = std::move(current.content);
}

// Clang otherwise inlines this state into lift_node, exhausting small worker stacks on deep documents.
MARKTIP_NOINLINE void process_inline(Document& document, std::size_t index, const NodeSpec& parent_spec,
                                     bool html, PathStack& path) {
    std::vector<std::size_t> original = std::move(document.node(index).content);
    std::vector<InlinePiece> pieces;
    pieces.reserve(original.size());
    std::vector<OpenMark> open;
    std::vector<Mark> effective;
    const Schema& schema = document.schema();
    for (std::size_t child : original) {
        if (document.node(child).type != "htmlInline") {
            apply_declared_marks(document.node(child).marks, effective, schema, path);
            pieces.push_back({InlinePieceKind::Node, child, nullptr});
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
    build_containers(document, index, parent_spec, pieces, std::move(original), path);
}

void lift_node(Document& document, std::size_t index, bool html, PathStack& path) {
    const NodeSpec& spec = *document.schema().node(document.node(index).type);
    if (spec.allow == ContentModel::Inlines) {
        process_inline(document, index, spec, html, path);
        return;
    }
    for (std::size_t i = 0; i < document.node(index).content.size(); ++i) {
        path.push_back({"content", i});
        lift_node(document, document.node(index).content[i], html, path);
        path.pop_back();
    }
}

}  // namespace

void lift(Document& document, bool html) {
    PathStack path;
    path.reserve(32);
    lift_node(document, 0, html, path);
}

}  // namespace marktip
