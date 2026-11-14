#include "schema_builder.h"

#include <algorithm>
#include <stdexcept>
#include <string_view>
#include <unordered_set>
#include <utility>

namespace marktip {
namespace {

bool ascii_letter(char value) {
    return (value >= 'A' && value <= 'Z') || (value >= 'a' && value <= 'z');
}

bool ascii_digit(char value) {
    return value >= '0' && value <= '9';
}

bool tag_name(std::string_view name) {
    if (name.empty() || !ascii_letter(name.front())) {
        return false;
    }
    return std::all_of(name.begin() + 1, name.end(), [](char value) {
        return ascii_letter(value) || ascii_digit(value) || value == '-';
    });
}

bool attr_name(std::string_view name) {
    auto initial = [](char value) { return ascii_letter(value) || value == '_' || value == ':'; };
    if (name.empty() || !initial(name.front())) {
        return false;
    }
    return std::all_of(name.begin() + 1, name.end(), [&](char value) {
        return initial(value) || ascii_digit(value) || value == '.' || value == '-';
    });
}

std::string ascii_lower(std::string value) {
    for (char& letter : value) {
        if (letter >= 'A' && letter <= 'Z') {
            letter = static_cast<char>(letter + ('a' - 'A'));
        }
    }
    return value;
}

bool value_type(const AttrValue& value, AttrRule rule) {
    return (rule == AttrRule::Str && value.kind == AttrValue::Kind::String) ||
           (rule == AttrRule::Int && value.kind == AttrValue::Kind::Int) ||
           (rule == AttrRule::Bool && value.kind == AttrValue::Kind::Bool);
}

AttrSpec compile_attr(const AttrDeclaration& declaration) {
    if (!attr_name(declaration.name)) {
        throw std::invalid_argument("invalid attr name '" + declaration.name + "'");
    }
    if (declaration.choices) {
        for (const AttrValue& value : *declaration.choices) {
            if (!value_type(value, declaration.rule)) {
                throw std::invalid_argument("choices for attr '" + declaration.name + "' must match its type");
            }
        }
    }
    if (declaration.fallback && !value_type(*declaration.fallback, declaration.rule)) {
        throw std::invalid_argument("default for attr '" + declaration.name + "' must match its type");
    }
    if (declaration.fallback && declaration.choices &&
        std::find(declaration.choices->begin(), declaration.choices->end(), *declaration.fallback) ==
            declaration.choices->end()) {
        throw std::invalid_argument("default for attr '" + declaration.name + "' must be in choices");
    }
    if (declaration.required && declaration.fallback) {
        throw std::invalid_argument("attr '" + declaration.name + "' cannot have both required and default");
    }
    UriKind uri = UriKind::None;
    if (declaration.uri) {
        if (*declaration.uri != "link" && *declaration.uri != "image") {
            throw std::invalid_argument("uri for attr '" + declaration.name + "' must be 'link' or 'image'");
        }
        if (declaration.rule != AttrRule::Str) {
            throw std::invalid_argument("uri requires a str attr: '" + declaration.name + "'");
        }
        if (declaration.fallback) {
            throw std::invalid_argument("attr '" + declaration.name + "' cannot have both uri and default");
        }
        uri = *declaration.uri == "link" ? UriKind::Link : UriKind::Image;
    }
    return {declaration.name, declaration.rule, NullAttr::Unset, MarkdownForm::Carried,
            declaration.required ? Presence::Required : Presence::Optional, {},
            declaration.choices, declaration.fallback, uri};
}

std::vector<AttrSpec> compile_attrs(const std::vector<AttrDeclaration>& declarations) {
    std::vector<AttrSpec> specs;
    std::unordered_set<std::string> names;
    for (const AttrDeclaration& declaration : declarations) {
        if (!names.insert(declaration.name).second) {
            throw std::invalid_argument("duplicate attr name '" + declaration.name + "'");
        }
        specs.push_back(compile_attr(declaration));
    }
    return specs;
}

std::vector<std::string> groups_from_declaration(const NodeDeclaration& declaration) {
    std::string_view group = declaration.group ? std::string_view(*declaration.group) : std::string_view("inline");
    std::vector<std::string> groups;
    std::size_t off = 0;
    while (off < group.size()) {
        off = group.find_first_not_of(" \t\n\r\f\v", off);
        if (off == std::string_view::npos) {
            break;
        }
        std::size_t end = group.find_first_of(" \t\n\r\f\v", off);
        if (end == std::string_view::npos) {
            end = group.size();
        }
        groups.emplace_back(group.substr(off, end - off));
        off = end;
    }
    return groups;
}

}  // namespace

std::shared_ptr<Schema> SchemaBuilder::build(std::vector<MarkDeclaration> marks, std::vector<NodeDeclaration> nodes) {
    std::shared_ptr<Schema> schema(new Schema);
    std::unordered_set<std::string> names;
    std::unordered_set<std::string> mark_names;
    std::unordered_set<std::string> tags;
    const std::unordered_set<std::string> reserved_tags = {
        "pre", "script", "style", "textarea", "br", "p", "h1", "h2", "h3", "h4", "h5", "h6",
        "blockquote", "ul", "ol", "li", "table", "tr", "th", "td", "img", "a",
    };
    auto check_type_and_tag = [&](const std::string& name, const std::optional<std::string>& declared_tag) {
        if (schema->node(name) != nullptr || schema->mark(name) != nullptr || !names.insert(name).second) {
            throw std::invalid_argument("duplicate type name '" + name + "'");
        }
        const std::string& tag = declared_tag ? *declared_tag : name;
        if (!tag_name(tag)) {
            throw std::invalid_argument("invalid tag name '" + tag + "'");
        }
        std::string folded_tag = ascii_lower(tag);
        if (reserved_tags.find(folded_tag) != reserved_tags.end()) {
            throw std::invalid_argument("reserved tag name '" + tag + "'");
        }
        if (!tags.insert(std::move(folded_tag)).second) {
            throw std::invalid_argument("duplicate tag name '" + tag + "'");
        }
    };
    for (const MarkDeclaration& declaration : marks) {
        check_type_and_tag(declaration.name, declaration.tag);
        mark_names.insert(declaration.name);
    }
    for (const NodeDeclaration& declaration : nodes) {
        check_type_and_tag(declaration.name, declaration.tag);
    }
    std::size_t order = 0;
    for (const MarkDeclaration& declaration : marks) {
        MarkSpec mark;
        mark.name = declaration.name;
        mark.core = false;
        mark.tag = declaration.tag ? *declaration.tag : declaration.name;
        mark.order = order++;
        mark.attrs = compile_attrs(declaration.attrs);
        if (std::holds_alternative<std::monostate>(declaration.excludes)) {
            mark.excludes.names.push_back(mark.name);
        } else if (const auto* all = std::get_if<std::string>(&declaration.excludes)) {
            if (*all != "_") {
                throw std::invalid_argument("excludes must be None, '_', or a tuple of mark names");
            }
            mark.excludes.all = true;
        } else {
            mark.excludes.names = std::get<std::vector<std::string>>(declaration.excludes);
            for (const std::string& name : mark.excludes.names) {
                if (Schema::gfm()->mark(name) == nullptr && mark_names.find(name) == mark_names.end()) {
                    throw std::invalid_argument("excludes names unknown mark '" + name + "'");
                }
            }
        }
        schema->marks_.push_back(std::move(mark));
    }
    std::vector<ContentType> content_types;
    for (const NodeSpec& node : schema->nodes_) {
        ContentType type {node.name, node.is_inline, {}};
        if (node.is_block) {
            type.groups.push_back("block");
        }
        if (node.is_inline) {
            type.groups.push_back("inline");
        }
        content_types.push_back(std::move(type));
    }
    std::size_t core_nodes = schema->nodes_.size();
    for (const NodeDeclaration& declaration : nodes) {
        if (declaration.kind != "inline") {
            throw std::invalid_argument("unsupported node kind '" + declaration.kind + "'");
        }
        std::vector<std::string> groups = groups_from_declaration(declaration);
        bool is_block = std::find(groups.begin(), groups.end(), "block") != groups.end();
        bool is_inline = std::find(groups.begin(), groups.end(), "inline") != groups.end();
        // Core block models read this membership directly,
        // so an inline shape here would be written as a block and read back inside a paragraph.
        if (is_block) {
            throw std::invalid_argument("inline node '" + declaration.name + "' cannot join block group");
        }
        Shape shape = declaration.content && !declaration.content->empty() ? Shape::InlineContainer : Shape::InlineAtom;
        schema->nodes_.push_back({declaration.name, compile_attrs(declaration.attrs), ContentModel::None,
                                  is_block, is_inline, false, declaration.tag ? *declaration.tag : declaration.name,
                                  shape});
        content_types.push_back({declaration.name, true, std::move(groups)});
        if (shape == Shape::InlineContainer) {
            schema->inline_containers_ = true;
        }
    }
    for (std::size_t i = 0; i < nodes.size(); ++i) {
        if (!nodes[i].content || nodes[i].content->empty()) {
            continue;
        }
        ContentDFA content = compile_content(*nodes[i].content, content_types);
        if (content.inline_content == false) {
            throw std::invalid_argument("inline node '" + nodes[i].name + "' cannot contain block content");
        }
        // Markdown does not carry the boundaries between adjacent text or raw HTML nodes.
        if (!content.idempotent("text") || !content.idempotent("htmlInline")) {
            throw std::invalid_argument(
                "content expression must not depend on how many adjacent text nodes there are; "
                "use text* or text+ (and htmlInline* or htmlInline+)");
        }
        schema->nodes_[core_nodes + i].dfa = static_cast<int>(schema->content_.size());
        schema->content_.push_back(std::move(content));
    }
    schema->declared_nodes_ = !nodes.empty();
    std::sort(schema->nodes_.begin(), schema->nodes_.end(),
              [](const NodeSpec& left, const NodeSpec& right) { return left.name < right.name; });
    std::sort(schema->marks_.begin(), schema->marks_.end(),
              [](const MarkSpec& left, const MarkSpec& right) { return left.name < right.name; });
    for (std::size_t i = 0; i < schema->marks_.size(); ++i) {
        const MarkSpec& mark = schema->marks_[i];
        if (!mark.core) {
            schema->tags_.push_back({mark.tag, true, i});
        }
    }
    for (std::size_t i = 0; i < schema->nodes_.size(); ++i) {
        const NodeSpec& node = schema->nodes_[i];
        if (!node.core) {
            schema->tags_.push_back({node.tag, false, i});
        }
    }
    std::sort(schema->tags_.begin(), schema->tags_.end(),
              [](const TagEntry& left, const TagEntry& right) { return left.tag < right.tag; });
    return schema;
}

}  // namespace marktip
