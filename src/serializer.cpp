#include "serializer.h"

#include <algorithm>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace marktip {
namespace {

std::string repeat(char ch, std::size_t count) {
    return std::string(count, ch);
}

std::vector<std::string> split_lines(const std::string& value) {
    std::vector<std::string> lines;
    std::size_t start = 0;
    while (start <= value.size()) {
        std::size_t end = value.find('\n', start);
        if (end == std::string::npos) {
            lines.push_back(value.substr(start));
            break;
        }
        lines.push_back(value.substr(start, end - start));
        start = end + 1;
    }
    return lines;
}

std::string rstrip_newlines(std::string value) {
    while (!value.empty() && value.back() == '\n') {
        value.pop_back();
    }
    return value;
}

std::size_t max_backtick_run(std::string_view value) {
    std::size_t best = 0;
    std::size_t current = 0;
    for (char ch : value) {
        if (ch == '`') {
            current++;
            best = std::max(best, current);
        } else {
            current = 0;
        }
    }
    return best;
}

bool looks_like_entity(std::string_view value, std::size_t index) {
    std::size_t i = index + 1;
    std::size_t length = 0;
    while (i < value.size() && length < 48) {
        char ch = value[i];
        bool word = (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') ||
                    (ch >= '0' && ch <= '9') || ch == '#';
        if (!word) {
            break;
        }
        ++i;
        ++length;
    }
    return length > 0 && i < value.size() && value[i] == ';';
}

std::string escape_inline(std::string_view value, bool table_cell = false) {
    std::string out;
    out.reserve(value.size());
    for (std::size_t i = 0; i < value.size(); ++i) {
        char ch = value[i];
        bool escape = ch == '\\' || ch == '`' || ch == '*' || ch == '_' || ch == '[' || ch == ']' ||
                      ch == '(' || ch == ')' || ch == '#' || ch == '!' || ch == '~' ||
                      (table_cell && ch == '|');
        if (ch == '<') {
            char next = i + 1 < value.size() ? value[i + 1] : '\0';
            escape = (next >= 'a' && next <= 'z') || (next >= 'A' && next <= 'Z') ||
                     next == '/' || next == '!' || next == '?';
        } else if (ch == '&') {
            escape = looks_like_entity(value, i);
        }
        if (escape) {
            out.push_back('\\');
        }
        out.push_back(ch);
    }
    return out;
}

// Escape characters that would start a new block construct at the beginning of a
// paragraph line ('-', '+', '>', setext underlines, ordered-list markers).
std::string escape_line_starts(const std::string& value) {
    std::vector<std::string> lines = split_lines(value);
    std::string out;
    for (std::size_t li = 0; li < lines.size(); ++li) {
        std::string& line = lines[li];
        std::size_t start = 0;
        while (start < line.size() && start < 3 && line[start] == ' ') {
            ++start;
        }
        if (start < line.size()) {
            char first = line[start];
            if (first == '-' || first == '+' || first == '>') {
                line.insert(start, 1, '\\');
            } else if (first == '=') {
                if (line.find_first_not_of("= \t", start) == std::string::npos) {
                    line.insert(start, 1, '\\');
                }
            } else if (first >= '0' && first <= '9') {
                std::size_t digits_end = line.find_first_not_of("0123456789", start);
                if (digits_end != std::string::npos && digits_end - start <= 9 && line[digits_end] == '.' &&
                    (digits_end + 1 == line.size() || line[digits_end + 1] == ' ' ||
                     line[digits_end + 1] == '\t')) {
                    line.insert(digits_end, 1, '\\');
                }
            }
        }
        if (li != 0) {
            out.push_back('\n');
        }
        out += line;
    }
    return out;
}

std::string escape_link_destination(std::string_view value) {
    bool needs_angle = false;
    for (char ch : value) {
        if (ch == ' ' || ch == '\t' || ch == '(' || ch == ')') {
            needs_angle = true;
            break;
        }
    }

    std::string out;
    if (needs_angle) {
        out.push_back('<');
        for (char ch : value) {
            if (ch == '<' || ch == '>') {
                out.push_back('\\');
            }
            out.push_back(ch);
        }
        out.push_back('>');
        return out;
    }

    out.reserve(value.size());
    for (char ch : value) {
        if (ch == ')' || ch == '\\') {
            out.push_back('\\');
        }
        out.push_back(ch);
    }
    return out;
}

std::string escape_title(std::string_view value) {
    std::string out;
    out.reserve(value.size());
    for (char ch : value) {
        if (ch == '"' || ch == '\\') {
            out.push_back('\\');
        }
        out.push_back(ch);
    }
    return out;
}

std::string code_span(std::string_view value) {
    std::size_t ticks = std::max<std::size_t>(1, max_backtick_run(value) + 1);
    std::string fence(ticks, '`');
    bool pad = !value.empty() && (value.front() == '`' || value.back() == '`' ||
                                  value.front() == ' ' || value.back() == ' ');
    return fence + (pad ? " " : "") + std::string(value) + (pad ? " " : "") + fence;
}

std::string mark_attr_string(const Mark& mark, const char* name, std::string fallback = {}) {
    return attr_string(mark.attrs, name, std::move(fallback));
}

bool has_mark(const std::vector<Mark>& marks, std::string_view type) {
    return std::any_of(marks.begin(), marks.end(), [type](const Mark& mark) {
        return mark.type == type;
    });
}

std::string apply_marks(std::string rendered, const std::vector<Mark>& marks, bool skip_code = false) {
    for (auto it = marks.rbegin(); it != marks.rend(); ++it) {
        if (skip_code && it->type == "code") {
            continue;
        }
        if (it->type == "bold") {
            rendered = "**" + rendered + "**";
        } else if (it->type == "italic") {
            rendered = "*" + rendered + "*";
        } else if (it->type == "strike") {
            rendered = "~~" + rendered + "~~";
        } else if (it->type == "code") {
            rendered = code_span(rendered);
        } else if (it->type == "link") {
            std::string href = mark_attr_string(*it, "href");
            std::string title = mark_attr_string(*it, "title");
            rendered = "[" + rendered + "](" + escape_link_destination(href) +
                       (title.empty() ? "" : " \"" + escape_title(title) + "\"") + ")";
        }
    }
    return rendered;
}

// A run of consecutive inline nodes sharing the same marks, with its content
// already rendered. `marks` excludes "code" (code spans are atomic per run).
struct InlineRun {
    std::vector<Mark> marks;
    std::string content;
};

bool is_emphasis_mark(const Mark& mark) {
    return mark.type == "bold" || mark.type == "italic" || mark.type == "strike";
}

std::size_t common_prefix(const std::vector<Mark>& a, const std::vector<Mark>& b) {
    std::size_t limit = std::min(a.size(), b.size());
    std::size_t i = 0;
    while (i < limit && a[i] == b[i]) {
        ++i;
    }
    return i;
}

std::size_t first_emphasis_at_or_after(const std::vector<Mark>& marks, std::size_t from) {
    for (std::size_t i = from; i < marks.size(); ++i) {
        if (is_emphasis_mark(marks[i])) {
            return i;
        }
    }
    return marks.size();
}

std::string open_delimiter(const Mark& mark) {
    if (mark.type == "bold") {
        return "**";
    }
    if (mark.type == "italic") {
        return "*";
    }
    if (mark.type == "strike") {
        return "~~";
    }
    if (mark.type == "link") {
        return "[";
    }
    return "";
}

std::string close_delimiter(const Mark& mark) {
    if (mark.type == "bold") {
        return "**";
    }
    if (mark.type == "italic") {
        return "*";
    }
    if (mark.type == "strike") {
        return "~~";
    }
    if (mark.type == "link") {
        std::string href = mark_attr_string(mark, "href");
        std::string title = mark_attr_string(mark, "title");
        return "](" + escape_link_destination(href) +
               (title.empty() ? "" : " \"" + escape_title(title) + "\"") + ")";
    }
    return "";
}

// Whitespace adjacent to an emphasis delimiter prevents the delimiter from
// opening/closing and no markdown syntax can express it, so such whitespace is
// moved outside the emphasis marks (cf. prosemirror-markdown
// expelEnclosingWhitespace). It stays inside enclosing non-emphasis marks
// such as links, which have no whitespace restriction.
void expel_boundary_whitespace(std::vector<InlineRun>& runs) {
    static const char* const kWhitespace = " \t\n";
    const std::vector<Mark> no_marks;
    std::vector<InlineRun> result;

    for (std::size_t i = 0; i < runs.size(); ++i) {
        const std::vector<Mark>& prev = i > 0 ? runs[i - 1].marks : no_marks;
        const std::vector<Mark>& next = i + 1 < runs.size() ? runs[i + 1].marks : no_marks;
        InlineRun& run = runs[i];

        std::size_t opening_emphasis = first_emphasis_at_or_after(run.marks, common_prefix(prev, run.marks));
        if (opening_emphasis < run.marks.size()) {
            std::size_t body = run.content.find_first_not_of(kWhitespace);
            std::size_t lead_len = body == std::string::npos ? run.content.size() : body;
            if (lead_len > 0) {
                InlineRun lead;
                lead.marks.assign(run.marks.begin(), run.marks.begin() + opening_emphasis);
                lead.content = run.content.substr(0, lead_len);
                run.content.erase(0, lead_len);
                result.push_back(std::move(lead));
            }
        }

        InlineRun tail;
        bool has_tail = false;
        std::size_t closing_emphasis = first_emphasis_at_or_after(run.marks, common_prefix(run.marks, next));
        if (closing_emphasis < run.marks.size() && !run.content.empty()) {
            std::size_t body = run.content.find_last_not_of(kWhitespace);
            std::size_t keep = body == std::string::npos ? 0 : body + 1;
            if (keep < run.content.size()) {
                tail.marks.assign(run.marks.begin(), run.marks.begin() + closing_emphasis);
                tail.content = run.content.substr(keep);
                run.content.erase(keep);
                has_tail = true;
            }
        }

        if (!run.content.empty()) {
            InlineRun kept;
            kept.marks = run.marks;
            kept.content = std::move(run.content);
            result.push_back(std::move(kept));
        }
        if (has_tail) {
            result.push_back(std::move(tail));
        }
    }

    runs = std::move(result);
}

// Emit runs keeping shared marks open across run boundaries, so e.g.
// [a: bold][b: bold+italic] becomes "**a*b***" rather than "**a*****b***".
std::string emit_runs(const std::vector<InlineRun>& runs) {
    std::string out;
    std::vector<Mark> open;
    for (const InlineRun& run : runs) {
        std::size_t keep = common_prefix(open, run.marks);
        while (open.size() > keep) {
            out += close_delimiter(open.back());
            open.pop_back();
        }
        for (std::size_t j = keep; j < run.marks.size(); ++j) {
            out += open_delimiter(run.marks[j]);
            open.push_back(run.marks[j]);
        }
        out += run.content;
    }
    while (!open.empty()) {
        out += close_delimiter(open.back());
        open.pop_back();
    }
    return out;
}

class MarkdownWriter {
public:
    explicit MarkdownWriter(const Document& document) : document_(document) {}

    std::string render() {
        if (document_.root().type != "doc") {
            throw std::invalid_argument("root node must have type 'doc'");
        }
        return render_doc(document_.root());
    }

private:
    const Document& document_;

    std::string render_doc(const Node& node) {
        std::vector<std::string> blocks;
        for_each_child(node, [&](const Node& child) {
            std::string rendered = rstrip_newlines(render_block(child, 0));
            if (!rendered.empty()) {
                blocks.push_back(std::move(rendered));
            }
        });
        return join(blocks, "\n\n");
    }

    std::string render_blocks(const Node& node, int indent) {
        std::vector<std::string> blocks;
        for_each_child(node, [&](const Node& child) {
            std::string rendered = rstrip_newlines(render_block(child, indent));
            if (!rendered.empty()) {
                blocks.push_back(std::move(rendered));
            }
        });
        return join(blocks, "\n\n");
    }

    std::string render_block(const Node& node, int indent) {
        const std::string& type = node.type;
        if (type == "doc") {
            return render_doc(node);
        }
        if (type == "paragraph") {
            return add_indent(escape_line_starts(render_inlines(node)), indent);
        }
        if (type == "heading") {
            long long level = std::clamp<long long>(attr_int(node.attrs, "level", 1), 1, 6);
            return add_indent(repeat('#', static_cast<std::size_t>(level)) + " " + render_inlines(node), indent);
        }
        if (type == "blockquote") {
            return render_blockquote(node, indent);
        }
        if (type == "bulletList") {
            return render_list(node, indent, false, false);
        }
        if (type == "orderedList") {
            return render_list(node, indent, true, false);
        }
        if (type == "taskList") {
            return render_list(node, indent, false, true);
        }
        if (type == "listItem" || type == "taskItem") {
            return render_list_item(node, "- ", indent);
        }
        if (type == "codeBlock") {
            return add_indent(render_code_block(node), indent);
        }
        if (type == "horizontalRule") {
            return add_indent("---", indent);
        }
        if (type == "table") {
            return add_indent(render_table(node), indent);
        }
        if (type == "htmlBlock") {
            return add_indent(attr_string(node.attrs, "html", plain_text(node)), indent);
        }
        if (type == "tableRow" || type == "tableHeader" || type == "tableCell") {
            return render_inlines(node);
        }
        if (type == "text" || type == "hardBreak" || type == "image" || type == "htmlInline") {
            return add_indent(render_inline(node), indent);
        }
        return add_indent(render_blocks(node, indent), 0);
    }

    std::string render_blockquote(const Node& node, int indent) {
        std::string inner = render_blocks(node, 0);
        std::vector<std::string> lines = split_lines(inner);
        std::string out;
        std::string prefix = repeat(' ', static_cast<std::size_t>(indent)) + "> ";
        std::string empty_prefix = repeat(' ', static_cast<std::size_t>(indent)) + ">";
        for (std::size_t i = 0; i < lines.size(); ++i) {
            if (i != 0) {
                out.push_back('\n');
            }
            out += lines[i].empty() ? empty_prefix : prefix + lines[i];
        }
        return out;
    }

    std::string render_list(const Node& node, int indent, bool ordered, bool task) {
        std::string out;
        long long number = attr_int(node.attrs, "start", 1);
        bool tight = attr_bool(node.attrs, "tight", true);
        std::size_t item_index = 0;
        for_each_child(node, [&](const Node& child) {
            if (item_index != 0) {
                out.push_back('\n');
                if (!tight) {
                    out.push_back('\n');
                }
            }

            std::string marker = ordered ? std::to_string(number++) + ". " : "- ";
            if (task || child.type == "taskItem") {
                marker += attr_bool(child.attrs, "checked", false) ? "[x] " : "[ ] ";
            }
            out += render_list_item(child, marker, indent);
            item_index++;
        });
        return out;
    }

    // Whether two adjacent blocks inside a list item need a blank line between
    // them to reparse as separate blocks. Blank lines are avoided where markdown
    // does not require them, so tight lists stay tight.
    static bool needs_blank_between(const std::string& prev, const std::string& next) {
        if (next == "paragraph" || next == "table" || next == "htmlBlock") {
            return true;
        }
        if (prev == "htmlBlock") {
            return true;
        }
        return prev == "blockquote" && next == "blockquote";
    }

    std::string render_list_item(const Node& node, const std::string& marker, int indent) {
        std::string body;
        const Node* prev = nullptr;
        for_each_child(node, [&](const Node& child) {
            if (prev != nullptr) {
                body.push_back('\n');
                if (needs_blank_between(prev->type, child.type)) {
                    body.push_back('\n');
                }
            }
            body += render_block(child, 0);
            prev = &child;
        });
        std::vector<std::string> lines = split_lines(body);
        std::string out = repeat(' ', static_cast<std::size_t>(indent)) + marker;
        if (lines.empty() || (lines.size() == 1 && lines[0].empty())) {
            return out;
        }

        out += lines[0];
        std::string continuation = repeat(' ', static_cast<std::size_t>(indent + static_cast<int>(marker.size())));
        for (std::size_t i = 1; i < lines.size(); ++i) {
            out.push_back('\n');
            if (!lines[i].empty()) {
                out += continuation;
                out += lines[i];
            }
        }
        return out;
    }

    std::string render_code_block(const Node& node) {
        std::string code = plain_text(node);
        std::size_t fence_len = std::max<std::size_t>(3, max_backtick_run(code) + 1);
        std::string fence(fence_len, '`');
        std::string language = attr_string(node.attrs, "language");
        if (language.empty()) {
            language = attr_string(node.attrs, "info");
        }

        std::string out = fence + language + "\n" + code;
        if (out.empty() || out.back() != '\n') {
            out.push_back('\n');
        }
        out += fence;
        return out;
    }

    std::string render_table(const Node& node) {
        std::vector<const Node*> rows;
        for_each_child(node, [&](const Node& child) {
            if (child.type == "tableRow") {
                rows.push_back(&child);
            }
        });
        if (rows.empty()) {
            return "";
        }

        std::size_t columns = 0;
        for (const Node* row : rows) {
            columns = std::max(columns, row_cells(*row).size());
        }
        if (columns == 0) {
            return "";
        }

        std::string out;
        out += render_table_row(*rows[0], columns);
        out.push_back('\n');
        out += render_table_delimiter(*rows[0], columns);
        for (std::size_t i = 1; i < rows.size(); ++i) {
            out.push_back('\n');
            out += render_table_row(*rows[i], columns);
        }
        return out;
    }

    std::string render_table_row(const Node& row, std::size_t columns) {
        std::vector<const Node*> cells = row_cells(row);
        std::string out = "|";
        for (std::size_t i = 0; i < columns; ++i) {
            out += " ";
            if (i < cells.size()) {
                out += table_cell_text(*cells[i]);
            }
            out += " |";
        }
        return out;
    }

    std::string render_table_delimiter(const Node& header, std::size_t columns) {
        std::vector<const Node*> cells = row_cells(header);
        std::string out = "|";
        for (std::size_t i = 0; i < columns; ++i) {
            std::string align = i < cells.size() ? attr_string(cells[i]->attrs, "align") : "";
            if (align == "left") {
                out += " :--- |";
            } else if (align == "center") {
                out += " :---: |";
            } else if (align == "right") {
                out += " ---: |";
            } else {
                out += " --- |";
            }
        }
        return out;
    }

    std::vector<const Node*> row_cells(const Node& row) {
        std::vector<const Node*> cells;
        for_each_child(row, [&](const Node& child) {
            if (child.type == "tableHeader" || child.type == "tableCell") {
                cells.push_back(&child);
            }
        });
        return cells;
    }

    std::string table_cell_text(const Node& cell) {
        std::string rendered;
        std::vector<std::string> blocks;
        for_each_child(cell, [&](const Node& child) {
            const std::string& type = child.type;
            if (type == "paragraph") {
                blocks.push_back(render_inlines(child, true));
            } else if (type == "text" || type == "hardBreak" || type == "image" || type == "htmlInline") {
                blocks.push_back(render_inline(child, true));
            } else {
                blocks.push_back(render_block(child, 0));
            }
        });
        rendered = join(blocks, "<br>");
        std::replace(rendered.begin(), rendered.end(), '\n', ' ');
        return rendered;
    }

    // Render one inline node without applying its marks. Marks are emitted by
    // emit_runs(), which keeps marks shared between consecutive runs open
    // across the boundary.
    std::string render_inline_content(const Node& node, bool table_cell, bool in_code) {
        const std::string& type = node.type;
        if (type == "text") {
            return in_code ? node.text : escape_inline(node.text, table_cell);
        }
        if (type == "hardBreak") {
            return table_cell ? "<br>" : "  \n";
        }
        if (type == "image") {
            std::string src = attr_string(node.attrs, "src");
            std::string alt = attr_string(node.attrs, "alt", plain_text(node));
            std::string title = attr_string(node.attrs, "title");
            return "![" + escape_inline(alt, table_cell) + "](" + escape_link_destination(src) +
                   (title.empty() ? "" : " \"" + escape_title(title) + "\"") + ")";
        }
        if (type == "htmlInline") {
            return attr_string(node.attrs, "html");
        }
        return render_inlines(node, table_cell);
    }

    std::string render_inlines(const Node& node, bool table_cell = false) {
        if (node.content.empty() && node.type == "text") {
            return render_inline(node, table_cell);
        }

        std::vector<InlineRun> runs = build_runs(node, table_cell);
        expel_boundary_whitespace(runs);
        return emit_runs(runs);
    }

    std::vector<InlineRun> build_runs(const Node& node, bool table_cell) {
        std::vector<InlineRun> runs;
        const std::vector<std::size_t>& content = node.content;
        std::size_t i = 0;
        while (i < content.size()) {
            const Node& first = document_.node(content[i]);
            bool in_code = has_mark(first.marks, "code");
            std::string group;
            std::size_t j = i;
            while (j < content.size()) {
                const Node& child = document_.node(content[j]);
                if (!(child.marks == first.marks)) {
                    break;
                }
                group += render_inline_content(child, table_cell, in_code);
                ++j;
            }

            InlineRun run;
            for (const Mark& mark : first.marks) {
                if (mark.type != "code") {
                    run.marks.push_back(mark);
                }
            }
            run.content = in_code ? code_span(group) : std::move(group);
            runs.push_back(std::move(run));
            i = j;
        }
        return runs;
    }

    std::string render_inline(const Node& node, bool table_cell = false) {
        bool in_code = has_mark(node.marks, "code");
        std::string rendered = render_inline_content(node, table_cell, in_code);
        if (in_code) {
            return apply_marks(code_span(rendered), node.marks, true);
        }
        return apply_marks(std::move(rendered), node.marks);
    }

    std::string plain_text(const Node& node) {
        const std::string& type = node.type;
        if (type == "text") {
            return node.text;
        }
        if (type == "hardBreak") {
            return "\n";
        }
        if (type == "htmlInline") {
            return attr_string(node.attrs, "html");
        }
        if (type == "htmlBlock") {
            return attr_string(node.attrs, "html");
        }
        if (type == "image") {
            return attr_string(node.attrs, "alt");
        }
        std::string out;
        for_each_child(node, [&](const Node& child) {
            out += plain_text(child);
        });
        return out;
    }

    template <typename Fn>
    void for_each_child(const Node& node, Fn&& fn) {
        for (std::size_t child : node.content) {
            fn(document_.node(child));
        }
    }

    std::string add_indent(std::string value, int indent) {
        if (indent <= 0 || value.empty()) {
            return value;
        }
        std::string prefix = repeat(' ', static_cast<std::size_t>(indent));
        std::vector<std::string> lines = split_lines(value);
        std::string out;
        for (std::size_t i = 0; i < lines.size(); ++i) {
            if (i != 0) {
                out.push_back('\n');
            }
            out += prefix + lines[i];
        }
        return out;
    }

    std::string join(const std::vector<std::string>& parts, std::string_view separator) {
        std::string out;
        std::size_t size = 0;
        for (const auto& part : parts) {
            size += part.size();
        }
        size += separator.size() * (parts.empty() ? 0 : parts.size() - 1);
        out.reserve(size);
        for (std::size_t i = 0; i < parts.size(); ++i) {
            if (i != 0) {
                out.append(separator.data(), separator.size());
            }
            out += parts[i];
        }
        return out;
    }
};

}  // namespace

std::string to_markdown(const Document& document) {
    MarkdownWriter writer(document);
    return writer.render();
}

}  // namespace marktip
