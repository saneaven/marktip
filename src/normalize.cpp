#include "normalize.h"

#include "md4c.h"

#include <algorithm>
#include <array>
#include <cstring>

#include "ast.h"
#include "form.h"
#include "inline_runs.h"
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
        const Node& node = document.node(child);
        bool paragraph = node.type == "paragraph";
        if (!paragraph && is_empty_list_or_table(node)) {
            continue;
        }
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

NodeKind normalize_text(Node& node, bool in_code) {
    normalize_newlines(node.text);
    if (in_code) {
        std::replace(node.text.begin(), node.text.end(), '\n', ' ');
        return NodeKind::CodeText;
    }
    return NodeKind::Text;
}

void trim_before_soft_break(Document& document, const std::vector<std::size_t>& children, std::size_t& kept) {
    while (kept != 0) {
        Node& left = document.node(children[kept - 1]);
        if (std::string_view(left.type) != "text" || !is_blank(left.text.back()) || has_mark(left.marks, "code")) {
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
enum class LineScope { Paragraph, Heading, Declared, Code };
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
            if (kind != NodeKind::Text || (!is_blank(last.text.back()) && last.text.back() != '\n') ||
                has_mark(last.marks, "code")) {
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

enum class InlineMarkKind { Link, Strike, Italic, Bold, Code, Declared };

InlineMarkKind inline_mark_kind(std::string_view type) {
    if (type == "link") return InlineMarkKind::Link;
    if (type == "strike") return InlineMarkKind::Strike;
    if (type == "italic") return InlineMarkKind::Italic;
    if (type == "bold") return InlineMarkKind::Bold;
    if (type == "code") return InlineMarkKind::Code;
    return InlineMarkKind::Declared;
}

void order_inline_marks(std::vector<Mark>& marks, const std::vector<Mark>& previous) {
    std::array<std::size_t, 6> ranks;
    for (std::size_t k = 0; k < ranks.size(); ++k) {
        ranks[k] = previous.size() + k;
    }
    for (std::size_t i = previous.size(); i != 0; --i) {
        InlineMarkKind kind = inline_mark_kind(previous[i - 1].type);
        if (kind < InlineMarkKind::Code) {
            ranks[static_cast<std::size_t>(kind)] = i - 1;
        }
    }
    auto before = [&](const Mark& a, const Mark& b) {
        return ranks[static_cast<std::size_t>(inline_mark_kind(a.type))] <
               ranks[static_cast<std::size_t>(inline_mark_kind(b.type))];
    };
    // The rank is per type, so repeated marks retain their input occurrence order.
    if (!std::is_sorted(marks.begin(), marks.end(), before)) {
        std::stable_sort(marks.begin(), marks.end(), before);
    }
}

bool join_inline(Node& left, const Node& right, bool text) {
    if (left.type != right.type || !same_run_marks(left.marks, right.marks)) {
        return false;
    }
    if (text) {
        left.text += right.text;
    } else {
        if (find_attr(left.attrs, "html") == nullptr || find_attr(right.attrs, "html") == nullptr) {
            return false;
        }
        std::string joined = attr_string(left.attrs, "html");
        joined += attr_string(right.attrs, "html");
        set_attr(left.attrs, "html", AttrValue::string(std::move(joined)));
    }
    return true;
}

struct EmphasisRun {
    std::size_t begin;
    std::size_t end;
    std::vector<Mark> marks;
    bool code;
};

struct EdgeEdit {
    std::size_t position;
    std::size_t width;
    unsigned removed;
    bool trailing;
};

unsigned character_category(std::string_view text, bool trailing, bool cjk_friendly, MD_SIZE& width) {
    if (text.empty()) {
        width = 0;
        return MD_ATTN_SPACE;
    }
    if ((trailing ? text.back() : text.front()) == '\n') {
        width = 1;
        return MD_ATTN_SPACE;
    }
    if (trailing) {
        if (text.size() > 8) {
            text.remove_prefix(text.size() - 8);
        }
        return md_attention_before(text.data(), static_cast<MD_SIZE>(text.size()), cjk_friendly, &width);
    }
    auto size = static_cast<MD_SIZE>(std::min<std::size_t>(text.size(), 4));
    return md_attention_category(md_attention_codepoint(text.data(), size, false, &width), cjk_friendly);
}

unsigned inline_edge(const Node& node, bool trailing, bool cjk_friendly) {
    if (std::string_view(node.type) == "text") {
        MD_SIZE width;
        return character_category(node.text, trailing, cjk_friendly, width);
    }
    return node.type == "hardBreak" ? MD_ATTN_SPACE : MD_ATTN_PUNCT;
}

unsigned emphasis_at_edge(const std::vector<Mark>& marks, std::size_t prefix, unsigned inside,
                          unsigned outside, bool trailing) {
    unsigned removed = 0;
    for (std::size_t i = prefix; i < marks.size();) {
        unsigned mask = emphasis_bit(marks[i]);
        std::size_t end = i + 1;
        if (mask != 0) {
            // Bold and italic form one asterisk token.
            if (mask != 4) {
                while (end < marks.size()) {
                    unsigned bit = emphasis_bit(marks[end]);
                    if (bit == 0 || bit == 4) {
                        break;
                    }
                    mask |= bit;
                    ++end;
                }
            }
            unsigned outer = i == prefix ? outside : MD_ATTN_PUNCT;
            unsigned inner = end == marks.size() ? inside : MD_ATTN_PUNCT;
            unsigned flanking = trailing ? md_attention_flanking(inner, outer) : md_attention_flanking(outer, inner);
            if ((flanking & (trailing ? MD_ATTN_CLOSE : MD_ATTN_OPEN)) == 0) {
                removed |= mask;
            }
        }
        i = end;
    }
    return removed;
}

std::vector<EmphasisRun> emphasis_runs(const Document& document, const std::vector<std::size_t>& children,
                                      const std::vector<Mark>& enclosing, bool declared_nodes, bool extended) {
    std::vector<EmphasisRun> runs;
    for_each_inline_run(document, children, enclosing, declared_nodes, [&](const InlineRun& run) {
        runs.push_back({run.begin, run.end, run.delimiter_marks(document.schema(), extended), run.in_code});
    });
    return runs;
}

unsigned unwritable_edge_marks(const Document& document, const std::vector<std::size_t>& children,
                               const std::vector<EmphasisRun>& runs, std::size_t i,
                               unsigned inside, bool trailing, bool cjk_friendly) {
    const EmphasisRun& run = runs[i];
    const EmphasisRun* neighbour = trailing ? (i + 1 < runs.size() ? &runs[i + 1] : nullptr)
                                             : (i != 0 ? &runs[i - 1] : nullptr);
    const std::vector<Mark> no_marks;
    const auto& adjacent = neighbour == nullptr ? no_marks : neighbour->marks;
    std::size_t prefix = common_prefix(run.marks, adjacent);
    unsigned outside = MD_ATTN_SPACE;
    if (neighbour != nullptr) {
        std::size_t other = trailing ? neighbour->begin : neighbour->end - 1;
        bool adjacent_delimiter = adjacent.size() > prefix;
        // Closing and opening asterisks at the seam form one token.
        if (adjacent_delimiter && prefix < run.marks.size() && (emphasis_bit(run.marks[prefix]) & 3) != 0) {
            adjacent_delimiter = !std::all_of(adjacent.begin() + prefix, adjacent.end(), [](const Mark& mark) {
                return (emphasis_bit(mark) & 3) != 0;
            });
        }
        outside = adjacent_delimiter || neighbour->code ? MD_ATTN_PUNCT
            : inline_edge(document.node(children[other]), !trailing, cjk_friendly);
    }
    return emphasis_at_edge(run.marks, prefix, inside, outside, trailing);
}

bool could_trim_emphasis(const Node& node) {
    std::string_view type = node.type;
    if (node.marks.empty()) {
        return false;
    }
    if (type == "text") {
        auto letter = [](unsigned char ch) {
            return (ch >= '0' && ch <= '9') || (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z');
        };
        if (node.text.empty() || (letter(node.text.front()) && letter(node.text.back()))) {
            return false;
        }
    } else if (type != "hardBreak") {
        return false;
    }
    return std::any_of(node.marks.begin(), node.marks.end(), emphasis_bit);
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
    bool cjk_friendly;
    InputAttrKeys* present;
    PathStack path;

    void normalize_root();
    NodeKind normalize_node(std::size_t index, NodeKind kind, LineBreaks breaks, const std::vector<Mark>& enclosing);
    NodeKind normalize_prepared_child(std::size_t index, std::size_t position, NodeKind kind,
                                     LineBreaks breaks, const std::vector<Mark>& enclosing);
    NodeKind normalize_child(std::size_t index, std::size_t position, LineBreaks breaks = LineBreaks::Preserve);
    bool normalize_lines(std::size_t index, LineScope scope, LineBreaks breaks,
                         const std::vector<Mark>& enclosing = {});
    bool normalize_children(std::size_t index, const NodeSpec* spec = nullptr,
                            LineBreaks breaks = LineBreaks::Preserve);
    void normalize_marks(Node& node, const std::vector<Mark>& enclosing);
    bool expel_emphasis_edges(std::vector<std::size_t>& children);
    void apply_edge_edit(std::size_t index, const EdgeEdit& edit, std::vector<std::size_t>& output);
    void order_stored_marks(std::vector<Mark>& marks, const std::vector<Mark>& previous);
    bool remove_child(NodeKind kind) const;
};

void Normalizer::apply_edge_edit(std::size_t index, const EdgeEdit& edit, std::vector<std::size_t>& output) {
    auto remove = [&](Node& node) {
        node.marks.erase(std::remove_if(node.marks.begin(), node.marks.end(), [&](const Mark& mark) {
            return (emphasis_bit(mark) & edit.removed) != 0;
        }), node.marks.end());
    };
    Node& node = document.node(index);
    output.push_back(index);
    if (edit.width >= node.text.size()) {
        remove(node);
        return;
    }

    std::size_t cut = edit.trailing ? node.text.size() - edit.width : edit.width;
    Node tail {node.type, node.text.substr(cut), node.attrs, node.marks, {}};
    node.text.resize(cut);
    remove(edit.trailing ? tail : node);
    std::size_t tail_index = document.append_node(std::move(tail));
    if (present != nullptr) {
        present->resize(tail_index + 1);
        (*present)[tail_index] = (*present)[index];
    }
    output.push_back(tail_index);
}

bool Normalizer::expel_emphasis_edges(std::vector<std::size_t>& children) {
    auto runs = emphasis_runs(document, children, {}, declared_nodes, reorder_marks);
    const std::vector<Mark> no_marks;
    std::vector<EdgeEdit> edits;
    for (std::size_t i = 0; i < runs.size(); ++i) {
        const EmphasisRun& run = runs[i];
        if (run.code || run.marks.empty()) {
            continue;
        }
        for (bool trailing : {false, true}) {
            std::size_t position = trailing ? run.end - 1 : run.begin;
            const Node& node = document.node(children[position]);
            if (!could_trim_emphasis(node)) {
                continue;
            }
            MD_SIZE width;
            unsigned category = character_category(node.text, trailing, cjk_friendly, width);
            if ((category & (MD_ATTN_SPACE | MD_ATTN_PUNCT)) == 0) {
                continue;
            }
            unsigned inside = inline_edge(node, trailing, cjk_friendly);
            unsigned removed = unwritable_edge_marks(document, children, runs, i, inside, trailing, cjk_friendly);
            if (removed == 0) {
                continue;
            }
            if (category == MD_ATTN_SPACE) {
                while (width < node.text.size()) {
                    std::string_view remaining = node.text;
                    remaining = trailing ? remaining.substr(0, remaining.size() - width) : remaining.substr(width);
                    MD_SIZE step;
                    if (character_category(remaining, trailing, cjk_friendly, step) != MD_ATTN_SPACE) {
                        break;
                    }
                    width += step;
                }
            }
            edits.push_back({position, width, removed, trailing});
            break;
        }
    }
    if (edits.empty()) {
        return false;
    }

    std::vector<std::size_t> edited;
    edited.reserve(children.size() + edits.size());
    auto edit = edits.begin();
    for (std::size_t i = 0; i < children.size(); ++i) {
        if (edit != edits.end() && edit->position == i) {
            apply_edge_edit(children[i], *edit++, edited);
        } else {
            edited.push_back(children[i]);
        }
    }

    std::size_t kept = 0;
    for (std::size_t index : edited) {
        Node& node = document.node(index);
        if (node.marks.size() > 1) {
            order_stored_marks(node.marks, kept == 0 ? no_marks : document.node(edited[kept - 1]).marks);
        }
        NodeKind kind = node_kind(node.type);
        if (kept != 0 && (kind == NodeKind::Text || kind == NodeKind::HtmlInline) &&
            join_inline(document.node(edited[kept - 1]), node, kind == NodeKind::Text)) {
            continue;
        }
        edited[kept++] = index;
    }
    edited.resize(kept);
    children = std::move(edited);
    return true;
}

bool Normalizer::normalize_lines(std::size_t index, LineScope scope, LineBreaks breaks,
                                 const std::vector<Mark>& enclosing) {
    // Filling descendants can move the node arena.
    auto children = std::move(document.node(index).content);
    std::size_t kept = 0;
    // Declared textblocks and inline containers enclose their content in tags.
    LinePosition position = scope == LineScope::Declared ? LinePosition::Content : LinePosition::Start;
    char soft_break = breaks == LineBreaks::Preserve ? '\n' : ' ';
    for (std::size_t child : children) {
        normalize_marks(document.node(child), enclosing);
    }
    auto normalize_line_child_text = [&](Node& child, bool in_code) {
        NodeKind kind = normalize_text(child, in_code);
        if (scope != LineScope::Code && kind == NodeKind::Text) {
            normalize_line_text(document, children, child.text, kept, position, soft_break);
        } else if (!child.text.empty()) {
            position = LinePosition::Content;
        }
        return kind;
    };
    auto normalize_run = [&](const InlineRun& run) {
        for (std::size_t i = run.begin; i < run.end; ++i) {
            std::size_t child_index = children[i];
            Node& child = document.node(child_index);
            NodeKind kind = node_kind(child.type);
            if (kind == NodeKind::Text) {
                // Join before T1 and T5 so a CRLF can span the original nodes.
                while (i + 1 < run.end && std::string_view(document.node(children[i + 1]).type) == "text") {
                    child.text += document.node(children[++i]).text;
                }
                kind = normalize_line_child_text(child, run.in_code);
                if (child.text.empty()) {
                    continue;
                }
            } else if (kind == NodeKind::HardBreak) {
                position = LinePosition::Start;
                if (breaks == LineBreaks::FlatHeading) {
                    if (kept == 0 && scope == LineScope::Heading) {
                        continue;
                    }
                    child.type = "text";
                    child.text = " ";
                    kind = NodeKind::Text;
                }
            }
            // Line trimming may have dropped the preceding input node.
            if (child.marks.size() > 1 && kept != 0) {
                const auto& previous = document.node(children[kept - 1]).marks;
                if (!previous.empty()) {
                    order_stored_marks(child.marks, previous);
                }
            }
            bool text = kind == NodeKind::Text || kind == NodeKind::CodeText;
            bool html = kind == NodeKind::HtmlInline;
            if (!text && kind != NodeKind::HardBreak) {
                if (!html) {
                    normalize_prepared_child(child_index, i, kind, breaks, enclosing);
                }
                position = LinePosition::Content;
            }
            // A flattened break or trimmed text can leave new neighbours.
            if (kept != 0 && (text || html)) {
                Node& left = document.node(children[kept - 1]);
                if (join_inline(left, child, text)) {
                    continue;
                }
            }
            children[kept++] = child_index;
        }
    };
    if (children.size() == 1 && std::string_view(document.node(children.front()).type) == "text") {
        Node& child = document.node(children.front());
        normalize_line_child_text(child, has_mark(child.marks, "code"));
        kept = !child.text.empty();
    } else {
        for_each_inline_run(document, children, {}, declared_nodes, normalize_run);
    }
    if (kept != 0 && (scope == LineScope::Paragraph || scope == LineScope::Heading)) {
        trim_line_end(document, children, kept, node_kind(document.node(children[kept - 1]).type),
                      scope == LineScope::Paragraph);
    }
    children.resize(kept);
    if (scope != LineScope::Code && std::any_of(children.begin(), children.end(), [&](std::size_t child) {
            return could_trim_emphasis(document.node(child));
        })) {
        while (expel_emphasis_edges(children)) {
        }
    }
    document.node(index).content = std::move(children);
    return kept == 0;
}

void Normalizer::order_stored_marks(std::vector<Mark>& marks, const std::vector<Mark>& previous) {
    order_inline_marks(marks, previous);
    if (reorder_marks) {
        order_marks(marks, schema);
    }
}

void Normalizer::normalize_marks(Node& node, const std::vector<Mark>& enclosing) {
    if (node.marks.empty()) {
        return;
    }
    for (Mark& mark : node.marks) {
        if (std::string_view(mark.type) == "link") {
            remove_empty_title(mark.attrs);
        }
    }
    if (std::string_view(node.type) == "hardBreak") {
        node.marks.erase(std::remove_if(node.marks.begin(), node.marks.end(), [](const Mark& mark) {
            return std::string_view(mark.type) == "code";
        }), node.marks.end());
    }
    remove_enclosing_marks(node.marks, enclosing);
    if (node.marks.size() > 1) {
        order_stored_marks(node.marks, {});
    }
}

NodeKind Normalizer::normalize_child(std::size_t index, std::size_t position, LineBreaks breaks) {
    Node& node = document.node(index);
    NodeKind kind = node_kind(node.type);
    normalize_marks(node, {});
    return normalize_prepared_child(index, position, kind, breaks, {});
}

NodeKind Normalizer::normalize_prepared_child(std::size_t index, std::size_t position, NodeKind kind,
                                              LineBreaks breaks, const std::vector<Mark>& enclosing) {
    if (!declared_nodes) {
        return normalize_node(index, kind, breaks, enclosing);
    }
    path.push_back({"content", position});
    kind = normalize_node(index, kind, breaks, enclosing);
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
    normalize_marks(document.root(), {});
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

NodeKind Normalizer::normalize_node(std::size_t index, NodeKind kind, LineBreaks breaks,
                                    const std::vector<Mark>& enclosing) {
    Node& node = document.node(index);
    const NodeSpec* spec = nullptr;
    switch (kind) {
    case NodeKind::Text:
        return normalize_text(node, has_mark(node.marks, "code"));
    case NodeKind::HardBreak:
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
        break;
    case NodeKind::TableCell:
        if (!table_tags && node.content.size() > 1) {
            join_cell_paragraphs(document, index);
        }
        break;
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
        normalize_lines(index, LineScope::Code, LineBreaks::Preserve);
        return kind;
    case NodeKind::Other:
        if (!node.content.empty() && declared_nodes) {
            spec = schema.node(node.type);
            if (spec->shape == Shape::TextBlock) {
                normalize_lines(index, LineScope::Declared, breaks);
                return kind;
            }
            if (spec->shape == Shape::InlineContainer) {
                auto inner = enclosing_delimiters(schema, enclosing, node.marks);
                normalize_lines(index, LineScope::Declared, breaks, inner);
                return kind;
            }
        }
        break;
    case NodeKind::CodeText:
    case NodeKind::HtmlInline:
    case NodeKind::EmptyParagraph:
    case NodeKind::ParagraphContainer:
    case NodeKind::Container:
    case NodeKind::Removed:
        break;
    }
    if (!document.node(index).content.empty()) {
        normalize_children(index, spec, kind == NodeKind::TableCell ? LineBreaks::Cell : LineBreaks::Preserve);
    }
    if (fills_empty_paragraph(kind) && document.node(index).content.empty()) {
        document.append_child(index, Node {"paragraph", {}, {}, {}, {}});
    }
    return kind;
}

}  // namespace

bool has_unwritable_emphasis(const Document& document, const Node& node, bool cjk_friendly,
                             const std::vector<Mark>& enclosing) {
    const Schema& schema = document.schema();
    bool declared_nodes = schema.has_declared_nodes();
    auto runs = emphasis_runs(document, node.content, enclosing, declared_nodes,
                              schema.has_declared_marks() || schema.has_link_tag());
    for (std::size_t i = 0; i < runs.size(); ++i) {
        const EmphasisRun& run = runs[i];
        if (run.marks.empty()) {
            continue;
        }
        for (bool trailing : {false, true}) {
            std::size_t position = trailing ? run.end - 1 : run.begin;
            // The writer puts backticks at both edges of a code span.
            unsigned inside = run.code ? MD_ATTN_PUNCT
                : inline_edge(document.node(node.content[position]), trailing, cjk_friendly);
            if (unwritable_edge_marks(document, node.content, runs, i, inside, trailing, cjk_friendly)) {
                return true;
            }
        }
    }
    if (declared_nodes) {
        for (std::size_t index : node.content) {
            const Node& child = document.node(index);
            if (const NodeSpec* spec = declared_inline_spec(schema, child);
                spec != nullptr && spec->shape == Shape::InlineContainer) {
                auto inner = enclosing_delimiters(schema, enclosing, child.marks);
                if (has_unwritable_emphasis(document, child, cjk_friendly, inner)) {
                    return true;
                }
            }
        }
    }
    return false;
}

void normalize_document(Document& document, bool cjk_friendly, InputAttrKeys* present) {
    const Schema& schema = document.schema();
    Normalizer {document, schema, schema.has_declared_marks() || schema.has_link_tag(),
                !schema.node("paragraph")->tag.empty(), schema.has_declared_nodes(),
                !schema.node("heading")->tag.empty(), schema.has_table_tags(),
                schema.has_node_forms(), cjk_friendly, present, {}}.normalize_root();
}

void normalize_inherited_attrs(Document& document) {
    // Inheritance can change fence info, list tightness, table attrs, and a link's form and mark order.
    const Schema& schema = document.schema();
    normalize_inherited_node_attrs(document, document.root(), schema, schema.has_link_tag(), schema.has_node_forms());
}

}  // namespace marktip
