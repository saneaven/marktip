#include "form.h"

#include <algorithm>
#include <utility>

#include "ast.h"
#include "compiler.h"

namespace marktip {

bool has_tag_attr(const AttrList& attrs, const std::vector<AttrSpec>& specs) {
    return std::any_of(specs.begin(), specs.end(), [&](const AttrSpec& spec) {
        return spec.form == MarkdownForm::Tag && find_attr(attrs, spec.name) != nullptr;
    });
}

namespace {

bool omits_empty_paragraph(const Node& parent) {
    std::string_view type = parent.type;
    return parent.content.size() == 1 &&
           (type == "listItem" || type == "taskItem" || type == "tableCell" || type == "tableHeader" ||
            type == "blockquote");
}

bool different_cell_alignment(const Node& header, const Node& cell) {
    const AttrValue* column_align = find_attr(header.attrs, "align");
    const AttrValue* cell_align = find_attr(cell.attrs, "align");
    return column_align && cell_align ? !(*column_align == *cell_align) : column_align != cell_align;
}

bool has_line_break(const Document& document, const Node& node) {
    return std::any_of(node.content.begin(), node.content.end(), [&](std::size_t index) {
        const Node& child = document.node(index);
        if (child.type == "htmlInline") {
            if (const AttrValue* html = find_attr(child.attrs, "html")) {
                return html->string_value.find('\n') != std::string::npos;
            }
        }
        return child.type == "hardBreak" ||
               (child.type == "text" && child.text.find('\n') != std::string::npos) ||
               has_line_break(document, child);
    });
}

// A recursive form query would otherwise enlarge the ordinary paragraph-cell path.
MARKTIP_NOINLINE bool cell_child_needs_tag(const Document& document, const Node& child) {
    const NodeSpec& spec = *document.schema().node(child.type);
    if (spec.shape == Shape::TextBlock) {
        return !uses_cell_textblock_tag(spec) && !uses_tag_form(document, child, spec);
    }
    return spec.shape != Shape::BlockAtom;
}

}  // namespace

bool uses_cell_textblock_tag(const NodeSpec& spec) {
    return spec.core && spec.shape == Shape::TextBlock && !spec.tag.empty() && spec.name != "paragraph";
}

bool uses_tag_form(const Document& document, const Node& node, const NodeSpec& spec) {
    if (spec.tag.empty()) {
        return false;
    }
    if (!spec.core || has_tag_attr(node.attrs, spec.attrs)) {
        return true;
    }
    if (node.type == "heading" && has_line_break(document, node)) {
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
            const Node& header = document.node(node.content.front());
            if (row.content.size() != header.content.size() ||
                uses_tag_form(document, row, *schema.node(row.type))) {
                return true;
            }
            for (std::size_t column = 0; column < row.content.size(); ++column) {
                const Node& cell = document.node(row.content[column]);
                if ((cell.type == "tableHeader") != (row_index == 0) || cell.content.size() > 1 ||
                    (!cell.content.empty() && document.node(cell.content.front()).type != "paragraph" &&
                     cell_child_needs_tag(document, document.node(cell.content.front()))) ||
                    has_tag_attr(cell.attrs, schema.node(cell.type)->attrs) ||
                    (row_index != 0 && different_cell_alignment(document.node(header.content[column]), cell))) {
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

const NodeSpec* block_child_form(const Document& document, const Node& child, const Node* parent,
                                 ContentModel inherited, bool table_cell) {
    const NodeSpec& spec = *document.schema().node(child.type);
    if (!spec.core) {
        return &spec;
    }
    switch (inherited) {
        case ContentModel::ListItems:
        case ContentModel::OrderedListItems:
        case ContentModel::TaskItems:
            if (child.type == "listItem" || child.type == "taskItem") return &spec;
            break;
        case ContentModel::Rows:
            if (child.type == "tableRow") return &spec;
            break;
        case ContentModel::Cells:
            if (is_table_cell(child.type)) return &spec;
            break;
        default:
            break;
    }
    if (parent != nullptr && child.type == "paragraph" && child.content.empty() && !spec.tag.empty() &&
        !omits_empty_paragraph(*parent)) {
        return &spec;
    }
    return (table_cell && uses_cell_textblock_tag(spec)) || uses_tag_form(document, child, spec) ? &spec : nullptr;
}

BlockKind block_kind(const Node& node, const NodeSpec* spec, const Schema& schema) {
    if (spec != nullptr) {
        if (spec->shape == Shape::TextBlock) {
            return BlockKind::TextBlock;
        }
        if (spec->shape == Shape::BlockAtom) {
            return BlockKind::TagLine;
        }
        if (spec->shape == Shape::InlineAtom || spec->shape == Shape::InlineContainer) {
            return BlockKind::Inline;
        }
    }
    const std::string& type = node.type;
    if (type == "paragraph") {
        return BlockKind::Paragraph;
    }
    if (type == "image") {
        return schema.block_image() ? BlockKind::Image : BlockKind::Inline;
    }
    if (type == "text" || type == "hardBreak" || type == "htmlInline") {
        return BlockKind::Inline;
    }
    if (type == "htmlBlock") {
        return BlockKind::Html;
    }
    if (type == "blockquote") {
        return BlockKind::Blockquote;
    }
    if (type == "table") {
        return BlockKind::Table;
    }
    if (type == "heading") {
        return BlockKind::Heading;
    }
    if (type == "codeBlock") {
        return BlockKind::FencedCode;
    }
    if (type == "horizontalRule") {
        return BlockKind::ThematicBreak;
    }
    if (type == "orderedList" && attr_int(node.attrs, "start", 1) != 1) {
        return BlockKind::NonInterruptingList;
    }
    return BlockKind::Other;
}

// Blank lines separate blocks where Markdown requires them.
bool needs_blank_between(BlockKind prev, BlockKind next) {
    if (prev == BlockKind::Heading || prev == BlockKind::FencedCode || prev == BlockKind::ThematicBreak) {
        return false;
    }
    if (prev == BlockKind::TextBlock || next == BlockKind::TextBlock) {
        return true;
    }
    if (prev == BlockKind::Html ||
        (prev == BlockKind::Table &&
         (next == BlockKind::Heading || next == BlockKind::FencedCode || next == BlockKind::TagLine))) {
        return true;
    }
    if (prev == BlockKind::TagLine || next == BlockKind::TagLine) {
        return false;
    }
    if ((prev == BlockKind::Image && (next == BlockKind::Paragraph || next == BlockKind::Image)) ||
        (prev == BlockKind::Paragraph && next == BlockKind::Image)) {
        return false;
    }
    if (next == BlockKind::Paragraph || next == BlockKind::Image || next == BlockKind::Table ||
        next == BlockKind::Html) {
        return true;
    }
    if ((prev == BlockKind::Paragraph || prev == BlockKind::Image) &&
        next == BlockKind::NonInterruptingList) {
        return true;
    }
    return prev == BlockKind::Blockquote && next == BlockKind::Blockquote;
}

std::string_view fence_info_word(std::string_view line) {
    constexpr auto whitespace = " \t\r\n\f\v";
    // MD4C skips only spaces before taking the first fence word.
    std::size_t begin = line.find_first_not_of(' ');
    if (begin == std::string_view::npos) {
        return {};
    }
    return line.substr(begin, line.find_first_of(whitespace, begin) - begin);
}

CodeInfo code_info(const AttrList& attrs) {
    std::string language = attr_string(attrs, "language");
    std::string info = attr_string(attrs, "info");
    const char* field = language.empty() ? "info" : "language";

    // A newline in the emitted info would move its tail into the code body.
    info.erase(std::min(info.size(), info.find_first_of("\r\n")));
    std::string value = language.empty() || language == fence_info_word(info) ? std::move(info) : std::move(language);
    value.erase(std::min(value.size(), value.find_first_of("\r\n")));
    std::string word(fence_info_word(value));
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
