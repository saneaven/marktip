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

std::string escape_inline(std::string_view value, bool table_cell = false) {
    std::string out;
    out.reserve(value.size());
    for (char ch : value) {
        bool escape = ch == '\\' || ch == '`' || ch == '*' || ch == '_' || ch == '[' || ch == ']' ||
                      ch == '(' || ch == ')' || ch == '#' || ch == '!' || ch == '~' ||
                      (table_cell && ch == '|');
        if (escape) {
            out.push_back('\\');
        }
        out.push_back(ch);
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
            return add_indent(render_inlines(node), indent);
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
        std::size_t item_index = 0;
        for_each_child(node, [&](const Node& child) {
            if (item_index != 0) {
                out.push_back('\n');
            }

            std::string marker;
            if (task) {
                bool checked = attr_bool(child.attrs, "checked", false);
                marker = checked ? "- [x] " : "- [ ] ";
            } else if (ordered) {
                marker = std::to_string(number++) + ". ";
            } else {
                marker = "- ";
            }
            out += render_list_item(child, marker, indent);
            item_index++;
        });
        return out;
    }

    std::string render_list_item(const Node& node, const std::string& marker, int indent) {
        std::vector<std::string> parts;
        for_each_child(node, [&](const Node& child) {
            parts.push_back(render_block(child, 0));
        });

        std::string body = join(parts, "\n");
        std::vector<std::string> lines = split_lines(body);
        std::string out = repeat(' ', static_cast<std::size_t>(indent)) + marker;
        if (lines.empty() || (lines.size() == 1 && lines[0].empty())) {
            return out;
        }

        out += lines[0];
        std::string continuation = repeat(' ', static_cast<std::size_t>(indent + static_cast<int>(marker.size())));
        for (std::size_t i = 1; i < lines.size(); ++i) {
            out.push_back('\n');
            out += continuation;
            out += lines[i];
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

    std::string render_inlines(const Node& node, bool table_cell = false) {
        std::string out;
        for_each_child(node, [&](const Node& child) {
            out += render_inline(child, table_cell);
        });
        if (out.empty() && node.type == "text") {
            return render_inline(node, table_cell);
        }
        return out;
    }

    std::string render_inline(const Node& node, bool table_cell = false) {
        const std::string& type = node.type;
        if (type == "text") {
            if (has_mark(node.marks, "code")) {
                return apply_marks(code_span(node.text), node.marks, true);
            }
            return apply_marks(escape_inline(node.text, table_cell), node.marks);
        }
        if (type == "hardBreak") {
            return apply_marks("  \n", node.marks);
        }
        if (type == "image") {
            std::string src = attr_string(node.attrs, "src");
            std::string alt = attr_string(node.attrs, "alt", plain_text(node));
            std::string title = attr_string(node.attrs, "title");
            std::string rendered = "![" + escape_inline(alt, table_cell) + "](" + escape_link_destination(src) +
                                   (title.empty() ? "" : " \"" + escape_title(title) + "\"") + ")";
            return apply_marks(std::move(rendered), node.marks);
        }
        if (type == "htmlInline") {
            return apply_marks(attr_string(node.attrs, "html"), node.marks);
        }
        return render_inlines(node, table_cell);
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
