#include "form.h"

#include <algorithm>
#include <utility>

#include "ast.h"

namespace marktip {
namespace {

bool has_tag_attr(const AttrList& attrs, const std::vector<AttrSpec>& specs) {
    return std::any_of(specs.begin(), specs.end(), [&](const AttrSpec& spec) {
        return spec.form == MarkdownForm::Tag && find_attr(attrs, spec.name) != nullptr;
    });
}

}  // namespace

bool uses_tag_form(const Document& document, const Node& node, const NodeSpec& spec) {
    if (spec.tag.empty()) {
        return false;
    }
    if (!spec.core || has_tag_attr(node.attrs, spec.attrs)) {
        return true;
    }
    const Schema& schema = document.schema();
    if (schema.has_list_tags() &&
        (node.type == "bulletList" || node.type == "orderedList" || node.type == "taskList")) {
        for (std::size_t child : node.content) {
            const Node& item = document.node(child);
            if (uses_tag_form(document, item, *schema.node(item.type))) {
                return true;
            }
        }
    }
    if (schema.has_table_tags() && node.type == "table") {
        for (std::size_t row_index = 0; row_index < node.content.size(); ++row_index) {
            const Node& row = document.node(node.content[row_index]);
            if (uses_tag_form(document, row, *schema.node(row.type))) {
                return true;
            }
            for (std::size_t child : row.content) {
                const Node& cell = document.node(child);
                if ((cell.type == "tableHeader") != (row_index == 0) || cell.content.size() > 1 ||
                    std::any_of(cell.content.begin(), cell.content.end(), [&](std::size_t index) {
                        return document.node(index).type != "paragraph";
                    }) ||
                    uses_tag_form(document, cell, *schema.node(cell.type))) {
                    return true;
                }
            }
        }
    }
    return false;
}

bool uses_tag_form(const Mark& mark, const MarkSpec& spec) {
    return !spec.core || (!spec.tag.empty() && has_tag_attr(mark.attrs, spec.attrs));
}

CodeInfo code_info(const AttrList& attrs) {
    std::string value = attr_string(attrs, "language");
    const char* field = "language";
    if (value.empty()) {
        value = attr_string(attrs, "info");
        field = "info";
    }
    // An info string is a single line.
    // Everything after a newline would land in the code content on reparse,
    // so the tail is dropped rather than emitted.
    value.erase(std::min(value.size(), value.find_first_of("\r\n")));
    constexpr const char* whitespace = " \t\r\n\f\v";
    std::size_t begin = value.find_first_not_of(whitespace);
    std::size_t end = begin == std::string::npos ? begin : value.find_first_of(whitespace, begin);
    std::string word = begin == std::string::npos ? std::string {} : value.substr(begin, end - begin);
    return {std::move(value), std::move(word), field};
}

const AttrValue* carrier_body(const NodeSpec& spec, const AttrList& attrs) {
    if (attrs.size() != 1) {
        return nullptr;
    }
    const auto& attr = attrs.front();
    if (attr.first != spec.attrs[spec.body].name || attr.second.kind != AttrValue::Kind::String) {
        return nullptr;
    }
    return &attr.second;
}

const AttrValue* fence_body(const NodeSpec& spec, const AttrList& attrs, bool table_cell) {
    if (table_cell || spec.fence.empty()) {
        return nullptr;
    }
    const AttrValue* body = carrier_body(spec, attrs);
    if (body == nullptr || body->string_value.find('\r') != std::string::npos) {
        return nullptr;
    }
    bool leading = true;
    for (char ch : body->string_value) {
        if (ch == '\t' && leading) {
            return nullptr;
        }
        if (ch == '\n') {
            leading = true;
        } else if (ch != ' ' && ch != '\t' && ch != '\f' && ch != '\v') {
            leading = false;
        }
    }
    return body;
}

bool inline_math_body_allowed(std::string_view body, bool table_cell, bool marked) {
    if (body.empty() || body.find_first_of("\r\n$`") != std::string_view::npos ||
        (table_cell && body.find('|') != std::string_view::npos) ||
        (marked && body.find_first_of("*~[]") != std::string_view::npos)) {
        return false;
    }
    std::size_t end = body.size();
    while (end != 0 && body[end - 1] == '\\') {
        --end;
    }
    return (body.size() - end) % 2 == 0;
}

bool inline_math_boundary(std::string_view surrounding, bool before) {
    if (surrounding.empty()) {
        return true;
    }
    unsigned char ch = static_cast<unsigned char>(before ? surrounding.back() : surrounding.front());
    // ASCII boundaries prove flanking without a second Unicode classifier.
    return ch != '$' && ((ch >= '\t' && ch <= '\r') || ch == ' ' ||
                         (ch >= '!' && ch <= '/') || (ch >= ':' && ch <= '@') ||
                         (ch >= '[' && ch <= '`') || (ch >= '{' && ch <= '~'));
}

}  // namespace marktip
