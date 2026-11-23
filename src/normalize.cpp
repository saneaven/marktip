#include "normalize.h"

#include <algorithm>
#include <cstring>

#include "ast.h"
#include "form.h"
#include "schema.h"

namespace marktip {
namespace {

enum class NodeKind {
    Text, CodeText, HardBreak, Paragraph, Heading, OrderedList, TaskItem, Image, Table, CodeBlock, Container, Other
};

NodeKind node_kind(std::string_view type) {
    const char* name = type.data();
    switch (type.size()) {
    case 3:
        if (std::memcmp(name, "doc", 3) == 0) return NodeKind::Container;
        break;
    case 4:
        if (std::memcmp(name, "text", 4) == 0) return NodeKind::Text;
        break;
    case 5:
        if (std::memcmp(name, "table", 5) == 0) return NodeKind::Table;
        if (std::memcmp(name, "image", 5) == 0) return NodeKind::Image;
        break;
    case 7:
        if (std::memcmp(name, "heading", 7) == 0) return NodeKind::Heading;
        break;
    case 8:
        if (std::memcmp(name, "taskItem", 8) == 0) return NodeKind::TaskItem;
        if (std::memcmp(name, "listItem", 8) == 0 || std::memcmp(name, "tableRow", 8) == 0 ||
            std::memcmp(name, "taskList", 8) == 0) {
            return NodeKind::Container;
        }
        break;
    case 9:
        if (std::memcmp(name, "paragraph", 9) == 0) return NodeKind::Paragraph;
        if (std::memcmp(name, "hardBreak", 9) == 0) return NodeKind::HardBreak;
        if (std::memcmp(name, "codeBlock", 9) == 0) return NodeKind::CodeBlock;
        if (std::memcmp(name, "tableCell", 9) == 0) return NodeKind::Container;
        break;
    case 10:
        if (std::memcmp(name, "blockquote", 10) == 0 || std::memcmp(name, "bulletList", 10) == 0) {
            return NodeKind::Container;
        }
        break;
    case 11:
        if (std::memcmp(name, "orderedList", 11) == 0) return NodeKind::OrderedList;
        if (std::memcmp(name, "tableHeader", 11) == 0) return NodeKind::Container;
        break;
    }
    return NodeKind::Other;
}

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

long long table_columns(const Document& document, const Node& table) {
    long long columns = 0;
    for (std::size_t index : table.content) {
        const Node& row = document.node(index);
        if (row.type == "tableRow") {
            auto cells = std::count_if(row.content.begin(), row.content.end(), [&](std::size_t child) {
                const std::string& type = document.node(child).type;
                return type == "tableHeader" || type == "tableCell";
            });
            columns = std::max(columns, static_cast<long long>(cells));
        }
    }
    return columns;
}

void normalize_inherited_node_attrs(Document& document, Node& node, const Schema& schema, bool reorder_marks) {
    if (std::string_view(node.type) == "codeBlock") {
        normalize_fence_info(node.attrs);
    }
    if (reorder_marks && node.marks.size() > 1) {
        order_marks(node.marks, schema);
    }
    for (std::size_t child : node.content) {
        normalize_inherited_node_attrs(document, document.node(child), schema, reorder_marks);
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

void trim_before_soft_break(Document& document, const Node& parent, std::size_t& kept) {
    while (kept != 0) {
        Node& left = document.node(parent.content[kept - 1]);
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

void normalize_line_text(Document& document, const Node& parent, std::string& text, std::size_t& kept,
                         LinePosition& position) {
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
            trim_before_soft_break(document, parent, kept);
        }
        if (end == std::string::npos) {
            break;
        }
        if (position == LinePosition::Content) {
            text[write++] = '\n';
        }
        position = LinePosition::Start;
        read = end + 1;
        end = text.find('\n', read);
    }
    text.resize(write);
}

void trim_line_end(Document& document, Node& parent, std::size_t& kept, NodeKind kind, bool drop_breaks) {
    while (kept != 0) {
        Node& last = document.node(parent.content[kept - 1]);
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
            kind = node_kind(document.node(parent.content[kept - 1]).type);
        }
    }
}

struct Normalizer {
    Document& document;
    const Schema& schema;
    bool reorder_marks;

    NodeKind normalize_node(Node& node);
    void normalize_lines(Node& parent, LineScope scope);
};

void Normalizer::normalize_lines(Node& parent, LineScope scope) {
    std::size_t kept = 0;
    // Declared nodes enclose their content in a tag.
    LinePosition position = scope == LineScope::Declared ? LinePosition::Content : LinePosition::Start;
    NodeKind last = NodeKind::Other;
    for (std::size_t index : parent.content) {
        Node& child = document.node(index);
        NodeKind kind = normalize_node(child);
        if (kind == NodeKind::Text) {
            normalize_line_text(document, parent, child.text, kept, position);
        } else if (kind == NodeKind::HardBreak) {
            position = LinePosition::Start;
        } else {
            position = LinePosition::Content;
        }
        if ((kind == NodeKind::Text || kind == NodeKind::CodeText) && child.text.empty()) {
            continue;
        }
        parent.content[kept++] = index;
        last = kind;
    }
    if (scope != LineScope::Declared) {
        trim_line_end(document, parent, kept, last, scope == LineScope::Paragraph);
    }
    parent.content.resize(kept);
}

NodeKind Normalizer::normalize_node(Node& node) {
    for (Mark& mark : node.marks) {
        if (std::string_view(mark.type) == "link") {
            remove_empty_title(mark.attrs);
        }
    }
    if (reorder_marks && node.marks.size() > 1) {
        order_marks(node.marks, schema);
    }
    NodeKind kind = node_kind(node.type);
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
        break;
    case NodeKind::Heading: {
        const AttrValue* level = find_attr(node.attrs, "level");
        if (level == nullptr || level->kind != AttrValue::Kind::Int || level->int_value < 1 || level->int_value > 6) {
            set_attr(node.attrs, "level", AttrValue::integer(std::clamp(attr_int(node.attrs, "level", 1), 1LL, 6LL)));
        }
        [[fallthrough]];
    }
    case NodeKind::Paragraph:
        normalize_lines(node, kind == NodeKind::Paragraph ? LineScope::Paragraph : LineScope::Heading);
        return kind;
    case NodeKind::TaskItem:
        if (find_attr(node.attrs, "checked") == nullptr) {
            set_attr(node.attrs, "checked", AttrValue::boolean(false));
        }
        break;
    case NodeKind::Image:
        if (find_attr(node.attrs, "alt") == nullptr) {
            set_attr(node.attrs, "alt", AttrValue::string(plain_text(document, node)));
        }
        node.content.clear();
        remove_empty_title(node.attrs);
        return kind;
    case NodeKind::Table:
        if (find_attr(node.attrs, "colCount") == nullptr) {
            set_attr(node.attrs, "colCount", AttrValue::integer(table_columns(document, node)));
        }
        break;
    case NodeKind::CodeBlock:
        normalize_fence_info(node.attrs);
        break;
    case NodeKind::Other:
        if (!node.content.empty() && schema.has_declared_nodes()) {
            const NodeSpec& spec = *schema.node(node.type);
            if (spec.shape == Shape::TextBlock || spec.shape == Shape::InlineContainer) {
                normalize_lines(node, LineScope::Declared);
                return kind;
            }
        }
        break;
    case NodeKind::CodeText:
    case NodeKind::Container:
        break;
    }
    for (std::size_t child : node.content) {
        normalize_node(document.node(child));
    }
    return kind;
}

}  // namespace

void normalize_document(Document& document) {
    const Schema& schema = document.schema();
    Normalizer {document, schema, schema.has_declared_marks() || schema.has_link_tag()}
        .normalize_node(document.root());
}

void normalize_inherited_attrs(Document& document) {
    // Inheritance can change fence info or switch a link's form and mark order.
    const Schema& schema = document.schema();
    normalize_inherited_node_attrs(document, document.root(), schema, schema.has_link_tag());
}

}  // namespace marktip
