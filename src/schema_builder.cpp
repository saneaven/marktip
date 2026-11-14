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

}  // namespace

std::shared_ptr<Schema> SchemaBuilder::build(std::vector<MarkDeclaration> declarations) {
    std::shared_ptr<Schema> schema(new Schema);
    std::unordered_set<std::string> names;
    std::unordered_set<std::string> tags;
    const std::unordered_set<std::string> reserved_tags = {
        "pre", "script", "style", "textarea", "br", "p", "h1", "h2", "h3", "h4", "h5", "h6",
        "blockquote", "ul", "ol", "li", "table", "tr", "th", "td", "img", "a",
    };
    for (const MarkDeclaration& declaration : declarations) {
        if (schema->node(declaration.name) != nullptr || schema->mark(declaration.name) != nullptr ||
            !names.insert(declaration.name).second) {
            throw std::invalid_argument("duplicate type name '" + declaration.name + "'");
        }
        const std::string& tag = declaration.tag ? *declaration.tag : declaration.name;
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
    }
    std::size_t order = 0;
    for (const MarkDeclaration& declaration : declarations) {
        MarkSpec mark;
        mark.name = declaration.name;
        mark.core = false;
        mark.tag = declaration.tag ? *declaration.tag : declaration.name;
        mark.order = order++;
        std::unordered_set<std::string> attrs;
        for (const AttrDeclaration& attr : declaration.attrs) {
            if (!attrs.insert(attr.name).second) {
                throw std::invalid_argument("duplicate attr name '" + attr.name + "'");
            }
            mark.attrs.push_back(compile_attr(attr));
        }
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
                if (Schema::gfm()->mark(name) == nullptr && names.find(name) == names.end()) {
                    throw std::invalid_argument("excludes names unknown mark '" + name + "'");
                }
            }
        }
        schema->marks_.push_back(std::move(mark));
    }
    std::sort(schema->marks_.begin(), schema->marks_.end(),
              [](const MarkSpec& left, const MarkSpec& right) { return left.name < right.name; });
    for (std::size_t i = 0; i < schema->marks_.size(); ++i) {
        const MarkSpec& mark = schema->marks_[i];
        if (!mark.core) {
            schema->tags_.push_back({mark.tag, i});
        }
    }
    std::sort(schema->tags_.begin(), schema->tags_.end(),
              [](const TagEntry& left, const TagEntry& right) { return left.tag < right.tag; });
    return schema;
}

}  // namespace marktip
