#include "normalize.h"

#include <algorithm>
#include <cstring>

#include "ast.h"
#include "form.h"
#include "lift.h"
#include "node_kind.h"
#include "schema.h"

namespace marktip {
namespace {

void normalize_fence_info(AttrList& attrs) {
    if (attrs.empty()) {
        return;
    }
    const AttrValue* language = find_attr(attrs, "language");
    const AttrValue* raw_info = find_attr(attrs, "info");
    if (raw_info == nullptr && language == nullptr) {
        return;
    }
    if (raw_info != nullptr && raw_info->kind == AttrValue::Kind::String) {
        const std::string_view info = raw_info->string_value;
        if (!info.empty() && info.front() != ' ' && info.back() != ' ' &&
            info.find_first_of("\r\n") == std::string_view::npos) {
            const std::string_view word = fence_info_word(info);
            const bool language_matches = word.empty() ? language == nullptr :
                language != nullptr && language->kind == AttrValue::Kind::String && language->string_value == word;
            if (language_matches) {
                return;
            }
        }
    }
    CodeInfo info = code_info(attrs);
    // The reader trims only spaces at the edges of the info string.
    std::size_t first = info.value.find_first_not_of(' ');
    if (first == std::string::npos) {
        info.value.clear();
    } else {
        info.value.erase(info.value.find_last_not_of(' ') + 1);
        info.value.erase(0, first);
    }
    auto store = [&](const char* key, std::string value) {
        auto stored = std::find_if(attrs.begin(), attrs.end(), [&](const auto& attr) {
            return attr.first == key;
        });
        if (value.empty()) {
            if (stored != attrs.end()) {
                attrs.erase(stored);
            }
        } else if (stored == attrs.end()) {
            attrs.emplace_back(key, AttrValue::string(std::move(value)));
        } else if (stored->second.kind != AttrValue::Kind::String || stored->second.string_value != value) {
            stored->second = AttrValue::string(std::move(value));
        }
    };
    store("language", std::move(info.word));
    store("info", std::move(info.value));
}

void remove_empty_title(AttrList& attrs) {
    auto title = std::find_if(attrs.begin(), attrs.end(), [](const auto& attr) {
        return attr.first == "title" && attr.second.kind == AttrValue::Kind::String &&
               attr.second.string_value.empty();
    });
    if (title != attrs.end()) {
        attrs.erase(title);
    }
}

void copy_cell_alignment(AttrList& attrs, const AttrValue* align) {
    auto old = std::find_if(attrs.begin(), attrs.end(), [](const auto& attr) { return attr.first == "align"; });
    if (old == attrs.end()) {
        if (align != nullptr) {
            attrs.emplace_back("align", *align);
        }
    } else if (align == nullptr) {
        attrs.erase(old);
    } else if (!(old->second == *align)) {
        old->second = *align;
    }
}

void normalize_pipe_alignment(Document& document, const Node& table) {
    const Node* header = nullptr;
    for (std::size_t row_index : table.content) {
        const Node& row = document.node(row_index);
        if (row.type != "tableRow") {
            continue;
        }
        if (header == nullptr) {
            header = &row;
            continue;
        }
        auto column = header->content.begin();
        for (std::size_t index : row.content) {
            Node& cell = document.node(index);
            if (!is_table_cell(cell.type)) {
                continue;
            }
            while (!is_table_cell(document.node(*column).type)) {
                ++column;
            }
            copy_cell_alignment(cell.attrs, find_attr(document.node(*column++).attrs, "align"));
        }
    }
}

void normalize_pipe_rows(Document& document, std::size_t index, std::size_t columns) {
    bool first = true;
    const std::size_t rows = document.node(index).content.size();
    for (std::size_t i = 0; i < rows; ++i) {
        std::size_t row = document.node(index).content[i];
        if (document.node(row).type != "tableRow") {
            continue;
        }
        std::string_view type = first ? std::string_view("tableHeader") : std::string_view("tableCell");
        std::size_t count = 0;
        for (std::size_t child : document.node(row).content) {
            Node& cell = document.node(child);
            if (cell.type == type) {
                ++count;
            } else if (is_table_cell(cell.type)) {
                cell.type = type;
                ++count;
            }
        }
        for (; count < columns; ++count) {
            document.append_child(row, Node {std::string(type), {}, {}, {}, {}});
        }
        first = false;
    }
    normalize_pipe_alignment(document, document.node(index));
}

void join_cell_paragraphs(Document& document, std::size_t index) {
    auto children = std::move(document.node(index).content);
    std::size_t kept = 0;
    bool previous_paragraph = false;
    for (std::size_t child : children) {
        bool paragraph = document.node(child).type == "paragraph";
        if (paragraph && previous_paragraph) {
            std::size_t joined = children[kept - 1];
            document.append_child(joined, Node {"hardBreak", {}, {}, {}, {}});
            auto& content = document.node(joined).content;
            const auto& extra = document.node(child).content;
            content.insert(content.end(), extra.begin(), extra.end());
        } else {
            children[kept++] = child;
        }
        previous_paragraph = paragraph;
    }
    children.resize(kept);
    document.node(index).content = std::move(children);
}

std::size_t normalize_table_width(const Document& document, Node& table) {
    std::size_t columns = table_columns(document, table);
    set_attr(table.attrs, "colCount", AttrValue::integer(static_cast<long long>(columns)));
    return columns;
}

struct ListItemSpacing {
    bool tight;
    bool has_previous = false;
    BlockKind previous = BlockKind::Other;

    bool add(BlockKind kind) {
        bool stop = has_previous && (!tight || needs_blank_between(previous, kind));
        has_previous = true;
        previous = kind;
        return stop;
    }
};

bool scan_list_item_pieces(const Document& document, const Node& parent, const NodeSpec* container,
                           bool node_forms, ListItemSpacing& spacing) {
    bool tag_lines = container != nullptr && !container->implicit;
    if (tag_lines && spacing.add(BlockKind::TagLine)) {
        return true;
    }
    ContentModel inherited = container != nullptr && container->core ? container->allow : ContentModel::None;
    for (std::size_t index : parent.content) {
        const Node& child = document.node(index);
        const NodeSpec* spec = node_forms ? block_child_form(document, child, &parent, inherited) : nullptr;
        if (spec != nullptr && spec->shape == Shape::BlockContainer) {
            if (scan_list_item_pieces(document, child, spec, node_forms, spacing)) {
                return true;
            }
        } else if (container == nullptr || spec != nullptr || child.type != "paragraph" || !child.content.empty()) {
            if (spacing.add(block_kind(child, spec, document.schema()))) {
                return true;
            }
        }
    }
    return tag_lines && spacing.add(BlockKind::TagLine);
}

void normalize_list_tightness(const Document& document, Node& list, bool node_forms) {
    bool tight = attr_bool(list.attrs, "tight", true);
    bool normalized = tight || list.content.size() == 1;
    if (normalized) {
        for (std::size_t index : list.content) {
            const Node& item = document.node(index);
            if (!node_forms && item.content.size() == 1) {
                continue;
            }
            ListItemSpacing spacing {tight};
            if (scan_list_item_pieces(document, item, nullptr, node_forms, spacing)) {
                normalized = false;
                break;
            }
        }
    }
    if (tight != normalized || find_attr(list.attrs, "tight") == nullptr) {
        set_attr(list.attrs, "tight", AttrValue::boolean(normalized));
    }
}

void normalize_inherited_node_attrs(Document& document, Node& node, const Schema& schema,
                                    bool reorder_marks, bool node_forms) {
    switch (node_kind(node.type)) {
    case NodeKind::CodeBlock:
        normalize_fence_info(node.attrs);
        break;
    case NodeKind::Table:
        normalize_table_width(document, node);
        if (!schema.has_table_tags()) {
            normalize_pipe_alignment(document, node);
        }
        break;
    case NodeKind::List:
    case NodeKind::OrderedList:
        normalize_list_tightness(document, node, node_forms);
        break;
    default:
        break;
    }
    if (reorder_marks && node.marks.size() > 1) {
        order_marks(node.marks, schema);
    }
    for (std::size_t child : node.content) {
        normalize_inherited_node_attrs(document, document.node(child), schema, reorder_marks, node_forms);
    }
}

bool is_blank(char ch) {
    return ch == ' ' || ch == '\t';
}

bool is_code(const Node& node) {
    return std::any_of(node.marks.begin(), node.marks.end(), [](const Mark& mark) {
        return std::string_view(mark.type) == "code";
    });
}

void normalize_newlines(std::string& text) {
    std::size_t write = text.find('\r');
    if (write == std::string::npos) {
        return;
    }
    for (std::size_t read = write; read < text.size(); ++read) {
        char ch = text[read];
        text[write++] = ch == '\r' ? '\n' : ch;
        if (ch == '\r' && read + 1 < text.size() && text[read + 1] == '\n') {
            ++read;
        }
    }
    text.resize(write);
}

void trim_before_soft_break(Document& document, const std::vector<std::size_t>& children, std::size_t& kept) {
    while (kept != 0) {
        Node& left = document.node(children[kept - 1]);
        if (std::string_view(left.type) != "text" || !is_blank(left.text.back()) || is_code(left)) {
            return;
        }
        left.text.erase(left.text.find_last_not_of(" \t") + 1);
        if (!left.text.empty()) {
            return;
        }
        --kept;
    }
}

enum class LinePosition { Start, Content };
enum class LineScope { Paragraph, Heading, Declared };
enum class LineBreaks { Preserve, Cell, FlatHeading };

void normalize_line_text(Document& document, const std::vector<std::size_t>& children, std::string& text,
                         std::size_t& kept, LinePosition& position, char soft_break) {
    std::size_t end = text.find('\n');
    if (end == std::string::npos) {
        if (position == LinePosition::Start && !text.empty() && is_blank(text.front())) {
            text.erase(0, text.find_first_not_of(" \t"));
        }
        if (!text.empty()) {
            position = LinePosition::Content;
        }
        return;
    }

    std::size_t write = 0;
    for (std::size_t read = 0;;) {
        std::size_t first = read;
        std::size_t last = std::min(end, text.size());
        while (position == LinePosition::Start && first < last && is_blank(text[first])) {
            ++first;
        }
        while (end != std::string::npos && first < last && is_blank(text[last - 1])) {
            --last;
        }
        if (first != last) {
            if (write != first) {
                std::memmove(text.data() + write, text.data() + first, last - first);
            }
            write += last - first;
            position = LinePosition::Content;
        } else if (read == 0 && end != std::string::npos && position == LinePosition::Content) {
            trim_before_soft_break(document, children, kept);
        }
        if (end == std::string::npos) {
            break;
        }
        if (position == LinePosition::Content) {
            text[write++] = soft_break;
        }
        position = LinePosition::Start;
        read = end + 1;
        end = text.find('\n', read);
    }
    text.resize(write);
}

void trim_line_end(Document& document, const std::vector<std::size_t>& children, std::size_t& kept, NodeKind kind,
                   bool drop_breaks) {
    while (kept != 0) {
        Node& last = document.node(children[kept - 1]);
        if (!drop_breaks || kind != NodeKind::HardBreak) {
            if (kind != NodeKind::Text || (!is_blank(last.text.back()) && last.text.back() != '\n') || is_code(last)) {
                return;
            }
            last.text.erase(last.text.find_last_not_of(" \t\n") + 1);
            if (!last.text.empty()) {
                return;
            }
        }
        --kept;
        if (kept != 0) {
            kind = node_kind(document.node(children[kept - 1]).type);
        }
    }
}

void flatten_heading_breaks(Document& document, std::vector<std::size_t>& children, std::size_t& kept,
                            LineScope scope) {
    std::size_t write = 0;
    bool after_break = false;
    for (std::size_t i = 0; i < kept; ++i) {
        std::size_t index = children[i];
        Node& child = document.node(index);
        bool hard_break = child.type == "hardBreak";
        if (hard_break) {
            if (write == 0 && scope == LineScope::Heading) {
                continue;
            }
            child.type = "text";
            child.text = " ";
        }
        if (write != 0 && (hard_break || after_break) && child.type == "text") {
            Node& left = document.node(children[write - 1]);
            if (left.type == "text" && left.marks == child.marks) {
                left.text += child.text;
                after_break = hard_break;
                continue;
            }
        }
        children[write++] = index;
        after_break = hard_break;
    }
    kept = write;
    if (kept != 0 && scope == LineScope::Heading) {
        trim_line_end(document, children, kept, node_kind(document.node(children[kept - 1]).type), false);
    }
}

struct Normalizer {
    Document& document;
    const Schema& schema;
    bool reorder_marks;
    bool paragraph_tags;
    bool declared_nodes;
    bool heading_tags;
    bool table_tags;
    bool node_forms;
    PathStack path;

    void normalize_root();
    NodeKind normalize_node(std::size_t index, LineBreaks breaks);
    NodeKind normalize_child(std::size_t index, std::size_t position, LineBreaks breaks = LineBreaks::Preserve);
    bool normalize_lines(std::size_t index, LineScope scope, LineBreaks breaks);
    bool normalize_children(std::size_t index, const NodeSpec* spec = nullptr,
                            LineBreaks breaks = LineBreaks::Preserve);
    void normalize_marks(Node& node);
    bool remove_child(NodeKind kind) const;
};

bool Normalizer::normalize_lines(std::size_t index, LineScope scope, LineBreaks breaks) {
    // Filling descendants can move the node arena.
    auto children = std::move(document.node(index).content);
    std::size_t kept = 0;
    // Declared textblocks and inline containers enclose their content in tags.
    LinePosition position = scope == LineScope::Declared ? LinePosition::Content : LinePosition::Start;
    NodeKind last = NodeKind::Other;
    char soft_break = breaks == LineBreaks::Preserve ? '\n' : ' ';
    bool hard_breaks = false;
    for (std::size_t i = 0; i < children.size(); ++i) {
        std::size_t child_index = children[i];
        NodeKind kind = normalize_child(child_index, i, breaks);
        Node& child = document.node(child_index);
        if (kind == NodeKind::Text) {
            normalize_line_text(document, children, child.text, kept, position, soft_break);
        } else if (kind == NodeKind::HardBreak) {
            position = LinePosition::Start;
            hard_breaks = true;
        } else {
            position = LinePosition::Content;
        }
        if ((kind == NodeKind::Text || kind == NodeKind::CodeText) && child.text.empty()) {
            continue;
        }
        children[kept++] = child_index;
        last = kind;
    }
    if (scope != LineScope::Declared) {
        trim_line_end(document, children, kept, last, scope == LineScope::Paragraph);
    }
    if (hard_breaks && breaks == LineBreaks::FlatHeading) {
        flatten_heading_breaks(document, children, kept, scope);
    }
    children.resize(kept);
    document.node(index).content = std::move(children);
    return kept == 0;
}

void Normalizer::normalize_marks(Node& node) {
    for (Mark& mark : node.marks) {
        if (std::string_view(mark.type) == "link") {
            remove_empty_title(mark.attrs);
        }
    }
    if (reorder_marks && node.marks.size() > 1) {
        order_marks(node.marks, schema);
    }
}

NodeKind Normalizer::normalize_child(std::size_t index, std::size_t position, LineBreaks breaks) {
    if (!declared_nodes) {
        return normalize_node(index, breaks);
    }
    path.push_back({"content", position});
    NodeKind kind = normalize_node(index, breaks);
    path.pop_back();
    return kind;
}

bool Normalizer::remove_child(NodeKind kind) const {
    return kind == NodeKind::Removed || (kind == NodeKind::EmptyParagraph && !paragraph_tags);
}

bool Normalizer::normalize_children(std::size_t index, const NodeSpec* spec, LineBreaks breaks) {
    auto children = std::move(document.node(index).content);
    std::size_t kept = 0;
    for (std::size_t i = 0; i < children.size(); ++i) {
        std::size_t child = children[i];
        if (!remove_child(normalize_child(child, i, breaks))) {
            children[kept++] = child;
        }
    }
    bool removed = kept != children.size();
    children.resize(kept);
    document.node(index).content = std::move(children);
    if (removed && spec != nullptr) {
        complete_content(document, index, *spec, path);
        return document.node(index).content.empty();
    }
    return kept == 0;
}

void update_spelling(Spelling& spelling, const std::vector<std::size_t>& children) {
    std::size_t child = 0;
    std::size_t kept = 0;
    for (SpellingPiece piece : spelling.items) {
        if (piece.has_node && children[child++] == 0) {
            if (!piece.text) {
                continue;
            }
            piece.has_node = false;
        }
        spelling.items[kept++] = piece;
    }
    spelling.items.resize(kept);
}

void Normalizer::normalize_root() {
    normalize_marks(document.root());
    auto children = std::move(document.root().content);
    std::size_t kept = 0;
    std::size_t last = 0;
    NodeKind last_kind = NodeKind::Other;
    for (std::size_t i = 0; i < children.size(); ++i) {
        NodeKind kind = normalize_child(children[i], i);
        if (remove_child(kind)) {
            // Zero marks a removed child without disturbing the spelling positions.
            children[i] = 0;
        } else {
            ++kept;
            last = i;
            last_kind = kind;
        }
    }
    if (kept == 1 && last_kind == NodeKind::EmptyParagraph) {
        children[last] = 0;
        --kept;
    }
    if (kept != children.size()) {
        if (document.spelling()) {
            update_spelling(*document.spelling(), children);
        }
        children.erase(std::remove(children.begin(), children.end(), 0), children.end());
    }
    document.root().content = std::move(children);
}

NodeKind Normalizer::normalize_node(std::size_t index, LineBreaks breaks) {
    Node& node = document.node(index);
    normalize_marks(node);
    NodeKind kind = node_kind(node.type);
    const NodeSpec* spec = nullptr;
    switch (kind) {
    case NodeKind::Text:
        normalize_newlines(node.text);
        if (is_code(node)) {
            std::replace(node.text.begin(), node.text.end(), '\n', ' ');
            kind = NodeKind::CodeText;
        }
        break;
    case NodeKind::HardBreak:
        node.marks.erase(std::remove_if(node.marks.begin(), node.marks.end(), [](const Mark& mark) {
            return std::string_view(mark.type) == "code";
        }), node.marks.end());
        break;
    case NodeKind::OrderedList:
        if (find_attr(node.attrs, "start") == nullptr) {
            set_attr(node.attrs, "start", AttrValue::integer(1));
        }
        [[fallthrough]];
    case NodeKind::List:
        if (normalize_children(index)) {
            return NodeKind::Removed;
        }
        normalize_list_tightness(document, document.node(index), node_forms);
        return kind;
    case NodeKind::Heading: {
        const AttrValue* level = find_attr(node.attrs, "level");
        if (level == nullptr || level->kind != AttrValue::Kind::Int || level->int_value < 1 || level->int_value > 6) {
            set_attr(node.attrs, "level", AttrValue::integer(std::clamp(attr_int(node.attrs, "level", 1), 1LL, 6LL)));
        }
        normalize_lines(index, LineScope::Heading, heading_tags ? breaks : LineBreaks::FlatHeading);
        return kind;
    }
    case NodeKind::Paragraph:
        return normalize_lines(index, LineScope::Paragraph, breaks) ? NodeKind::EmptyParagraph : kind;
    case NodeKind::TaskItem:
        if (find_attr(node.attrs, "checked") == nullptr) {
            set_attr(node.attrs, "checked", AttrValue::boolean(false));
        }
        [[fallthrough]];
    case NodeKind::ParagraphContainer:
    case NodeKind::TableCell:
        if (kind == NodeKind::TableCell && !table_tags && node.content.size() > 1) {
            join_cell_paragraphs(document, index);
        }
        if (normalize_children(index, nullptr, kind == NodeKind::TableCell ? LineBreaks::Cell : LineBreaks::Preserve)) {
            document.append_child(index, Node {"paragraph", {}, {}, {}, {}});
        }
        return kind;
    case NodeKind::Image:
        if (find_attr(node.attrs, "alt") == nullptr) {
            set_attr(node.attrs, "alt", AttrValue::string(plain_text(document, node)));
        }
        node.content.clear();
        remove_empty_title(node.attrs);
        return kind;
    case NodeKind::Table: {
        std::size_t columns = normalize_table_width(document, node);
        if (!table_tags) {
            normalize_pipe_rows(document, index, columns);
        }
        return normalize_children(index) ? NodeKind::Removed : kind;
    }
    case NodeKind::CodeBlock:
        normalize_fence_info(node.attrs);
        break;
    case NodeKind::Other:
        if (!node.content.empty() && declared_nodes) {
            spec = schema.node(node.type);
            if (spec->shape == Shape::TextBlock || spec->shape == Shape::InlineContainer) {
                normalize_lines(index, LineScope::Declared, breaks);
                return kind;
            }
        }
        break;
    case NodeKind::CodeText:
    case NodeKind::EmptyParagraph:
    case NodeKind::Container:
    case NodeKind::Removed:
        break;
    }
    if (!node.content.empty()) {
        normalize_children(index, spec);
    }
    return kind;
}

}  // namespace

void normalize_document(Document& document) {
    const Schema& schema = document.schema();
    Normalizer {document, schema, schema.has_declared_marks() || schema.has_link_tag(),
                !schema.node("paragraph")->tag.empty(), schema.has_declared_nodes(),
                !schema.node("heading")->tag.empty(), schema.has_table_tags(),
                schema.has_node_forms(), {}}.normalize_root();
}

void normalize_inherited_attrs(Document& document) {
    // Inheritance can change fence info, list tightness, table attrs, and a link's form and mark order.
    const Schema& schema = document.schema();
    normalize_inherited_node_attrs(document, document.root(), schema, schema.has_link_tag(), schema.has_node_forms());
}

}  // namespace marktip
