#include "serializer.h"

#include <algorithm>
#include <cstddef>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "errors.h"
#include "form.h"
#include "schema.h"
#include "tags.h"

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

void rstrip_newlines(std::string& value) {
    while (!value.empty() && value.back() == '\n') {
        value.pop_back();
    }
}

std::size_t max_run(std::string_view value, char of) {
    std::size_t best = 0;
    std::size_t current = 0;
    for (char ch : value) {
        if (ch == of) {
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

std::string escape_dollars(std::string value) {
    std::size_t first = value.find('$');
    if (first == std::string::npos) {
        return value;
    }
    std::string out;
    out.reserve(value.size());
    out.append(value.data(), first);
    for (std::size_t i = first; i < value.size(); ++i) {
        if (value[i] == '$') {
            out.push_back('\\');
        }
        out.push_back(value[i]);
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
    std::size_t ticks = std::max<std::size_t>(1, max_run(value, '`') + 1);
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

std::string apply_marks(std::string rendered, const std::vector<Mark>& marks, const Schema& schema,
                        bool skip_code = false) {
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
        } else {
            rendered = open_tag(schema, *it) + rendered + close_tag(schema, *it);
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

struct MathToken {
    const Node* node;
    const NodeSpec* spec;
};

// Where inline content is being rendered. TableCell and Heading are
// single-line contexts: cells express hard breaks as <br>, while ATX headings
// have no break syntax at all, so breaks there demote to a plain space.
enum class InlineContext { Default, TableCell, Heading };

// Adjacent lists of the same family would merge on reparse if they used the
// same marker, so sibling loops alternate the marker (variant 0/1) between
// consecutive same-family lists: "-" vs "*", "1. " vs "1) ".
enum class ListFamily { None, Bullet, Ordered };

enum class BlockKind { Paragraph, TextBlock, Inline, TagLine, Html, Blockquote, Table, List, Other };

struct BlockPiece {
    BlockPiece(std::string&& text, BlockKind kind, ListFamily family)
        : text(std::move(text)), kind(kind), family(family) {}

    std::string text;
    BlockKind kind;
    ListFamily family;
};

ListFamily list_family(const std::string& type) {
    if (type == "bulletList" || type == "taskList") {
        return ListFamily::Bullet;
    }
    if (type == "orderedList") {
        return ListFamily::Ordered;
    }
    return ListFamily::None;
}

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

std::string open_delimiter(const Mark& mark, const Schema& schema) {
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
    return open_tag(schema, mark);
}

std::string close_delimiter(const Mark& mark, const Schema& schema) {
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
    return close_tag(schema, mark);
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
            if (!run.marks.empty()) {
                kept.marks = run.marks;
            }
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
std::string emit_runs(const std::vector<InlineRun>& runs, const Schema& schema) {
    std::string out;
    std::vector<Mark> open;
    for (const InlineRun& run : runs) {
        std::size_t keep = common_prefix(open, run.marks);
        while (open.size() > keep) {
            out += close_delimiter(open.back(), schema);
            open.pop_back();
        }
        for (std::size_t j = keep; j < run.marks.size(); ++j) {
            out += open_delimiter(run.marks[j], schema);
            open.push_back(run.marks[j]);
        }
        out += run.content;
    }
    while (!open.empty()) {
        out += close_delimiter(open.back(), schema);
        open.pop_back();
    }
    return out;
}

class MarkdownWriter {
public:
    explicit MarkdownWriter(const Document& document)
        : document_(document), schema_(document.schema()), extended_(schema_.has_declared_marks()),
          declared_nodes_(schema_.has_declared_nodes()), inline_containers_(schema_.has_inline_containers()),
          math_(schema_.has_math()) {}

    std::string render() {
        if (document_.root().type != "doc") {
            throw InvalidNodeError("invalid_root", "type", "root node must have type 'doc'", "");
        }
        std::string rendered = render_doc(document_.root());
        if (!math_tokens_.empty()) {
            return resolve_math(std::move(rendered));
        }
        return rendered;
    }

private:
    const Document& document_;
    const Schema& schema_;
    bool extended_;
    bool declared_nodes_;
    bool inline_containers_;
    bool math_;
    std::vector<MathToken> math_tokens_;

    std::string escape_text(std::string_view value, bool table_cell) {
        std::string escaped = escape_inline(value, table_cell);
        if (math_) {
            escaped = escape_dollars(std::move(escaped));
        }
        return escaped;
    }

    std::string math_token(const Node& node, const NodeSpec& spec) {
        // Stored text has no NUL, so a marker survives escaping without matching document text.
        std::string token(1, '\0');
        token += std::to_string(math_tokens_.size());
        token.push_back('\0');
        math_tokens_.push_back({&node, &spec});
        return token;
    }

    std::string resolve_math(std::string rendered) {
        std::string out;
        out.reserve(rendered.size());
        std::size_t begin = 0;
        std::size_t marker = rendered.find('\0');
        while (marker != std::string::npos) {
            out.append(rendered.data() + begin, marker - begin);
            std::size_t end = marker + 1;
            std::size_t index = 0;
            while (rendered[end] != '\0') {
                index = index * 10 + static_cast<std::size_t>(rendered[end] - '0');
                ++end;
            }
            const MathToken& token = math_tokens_[index];
            std::string_view after(rendered.data() + end + 1, rendered.size() - end - 1);
            // Delimiters and expelled whitespace decide flanking only after the runs have been emitted.
            if (inline_math_boundary(out, true) && inline_math_boundary(after, false)) {
                out.push_back('$');
                out += token.node->attrs.front().second.string_value;
                out.push_back('$');
            } else {
                out += open_node_tag(*token.spec, token.node->attrs);
            }
            begin = end + 1;
            marker = rendered.find('\0', begin);
        }
        out.append(rendered.data() + begin, rendered.size() - begin);
        return out;
    }

    std::string render_doc(const Node& node) {
        return render_blocks(node, 0);
    }

    std::string render_blocks(const Node& node, int indent) {
        return join_block_pieces(block_pieces(node, indent, false), false);
    }

    const NodeSpec* declared_form(const Node& node) const {
        const NodeSpec& spec = *schema_.node(node.type);
        return spec.core ? nullptr : &spec;
    }

    static BlockKind block_kind(const Node& node, const NodeSpec* spec) {
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
        if (type == "text" || type == "hardBreak" || type == "image" || type == "htmlInline") {
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
        if (type == "bulletList" || type == "orderedList" || type == "taskList") {
            return BlockKind::List;
        }
        return BlockKind::Other;
    }

    std::vector<BlockPiece> block_pieces(const Node& node, int indent, bool list_item) {
        std::vector<BlockPiece> pieces;
        // Track the previously *emitted* sibling: an empty render must not
        // reset the alternation, or the lists around it would merge.
        int prev_variant = 0;
        collect_block_children(node, nullptr, indent, list_item, pieces, prev_variant);
        return pieces;
    }

    void append_container_tag(const Node& node, const NodeSpec& spec, int indent, bool closing,
                              std::vector<BlockPiece>& pieces, int& prev_variant) {
        std::string tag = closing ? close_node_tag(spec) : open_node_tag(spec, node.attrs);
        pieces.emplace_back(add_indent(std::move(tag), indent), BlockKind::TagLine, ListFamily::None);
        prev_variant = 0;
    }

    void collect_block_children(const Node& node, const NodeSpec* container, int indent, bool list_item,
                                std::vector<BlockPiece>& pieces, int& prev_variant) {
        pieces.reserve(node.content.size());
        if (container != nullptr && !container->implicit) {
            append_container_tag(node, *container, indent, false, pieces, prev_variant);
        }
        for_each_child(node, [&](const Node& child) {
            const NodeSpec* spec = declared_nodes_ ? declared_form(child) : nullptr;
            if (spec != nullptr && spec->shape == Shape::BlockContainer) {
                collect_block_children(child, spec, indent, list_item, pieces, prev_variant);
                return;
            }

            ListFamily family = list_family(child.type);
            int variant = (family != ListFamily::None && !pieces.empty() && pieces.back().family == family)
                              ? 1 - prev_variant : 0;
            std::string rendered = render_block(child, indent, spec, variant);
            if (!list_item) {
                rstrip_newlines(rendered);
            }
            if ((!list_item || container != nullptr) && rendered.empty()) {
                return;
            }
            pieces.emplace_back(std::move(rendered), list_item ? block_kind(child, spec) : BlockKind::Other, family);
            prev_variant = variant;
        });
        if (container != nullptr && !container->implicit) {
            append_container_tag(node, *container, indent, true, pieces, prev_variant);
        }
    }

    std::string join_block_pieces(std::vector<BlockPiece>&& pieces, bool list_item) {
        if (pieces.empty()) {
            return {};
        }
        std::string out = std::move(pieces.front().text);
        std::size_t size = out.size();
        for (std::size_t i = 1; i < pieces.size(); ++i) {
            size += pieces[i].text.size();
        }
        size += 2 * (pieces.size() - 1);
        out.reserve(size);
        for (std::size_t i = 1; i < pieces.size(); ++i) {
            if (!list_item || needs_blank_between(pieces[i - 1].kind, pieces[i].kind)) {
                out.append("\n\n");
            } else {
                out.push_back('\n');
            }
            out += pieces[i].text;
        }
        return out;
    }

    std::string render_declared(const Node& node, const NodeSpec& spec, int indent,
                                InlineContext ctx = InlineContext::Default) {
        if (spec.shape == Shape::BlockContainer) {
            std::vector<BlockPiece> pieces;
            int prev_variant = 0;
            collect_block_children(node, &spec, indent, false, pieces, prev_variant);
            return join_block_pieces(std::move(pieces), false);
        }
        if (spec.shape == Shape::TextBlock) {
            return add_indent(escape_line_starts(open_node_tag(spec, node.attrs) + render_inlines(node, ctx) +
                                                close_node_tag(spec)), indent);
        }
        if (spec.shape == Shape::BlockAtom) {
            if (const AttrValue* body = fence_body(spec, node.attrs, ctx == InlineContext::TableCell)) {
                return add_indent(render_fenced_code(body->string_value + "\n", spec.fence), indent);
            }
            return add_indent(open_node_tag(spec, node.attrs), indent);
        }
        return add_indent(render_inline(node, ctx), indent);
    }

    std::string render_block(const Node& node, int indent, const NodeSpec* spec, int list_variant = 0,
                             InlineContext ctx = InlineContext::Default) {
        if (spec != nullptr) {
            return render_declared(node, *spec, indent, ctx);
        }
        const std::string& type = node.type;
        if (type == "doc") {
            return render_doc(node);
        }
        if (type == "paragraph") {
            return add_indent(escape_line_starts(render_inlines(node)), indent);
        }
        if (type == "heading") {
            long long level = std::clamp<long long>(attr_int(node.attrs, "level", 1), 1, 6);
            return add_indent(
                repeat('#', static_cast<std::size_t>(level)) + " " + render_inlines(node, InlineContext::Heading),
                indent);
        }
        if (type == "blockquote") {
            return render_blockquote(node, indent);
        }
        if (type == "bulletList") {
            return render_list(node, indent, false, false, list_variant);
        }
        if (type == "orderedList") {
            return render_list(node, indent, true, false, list_variant);
        }
        if (type == "taskList") {
            return render_list(node, indent, false, true, list_variant);
        }
        if (type == "listItem" || type == "taskItem") {
            return render_list_item(node, "- ", indent, false);
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

    std::string render_list(const Node& node, int indent, bool ordered, bool task, int variant = 0) {
        std::string out;
        // "start": -5 would otherwise render as "-5. a", which is not a list at all on
        // reparse, and a 10-digit marker stops being a list marker as well.
        long long number = std::clamp<long long>(attr_int(node.attrs, "start", 1), 0, kMaxListStart);
        bool tight = attr_bool(node.attrs, "tight", true);
        std::size_t item_index = 0;
        for_each_child(node, [&](const Node& child) {
            if (item_index != 0) {
                out.push_back('\n');
                if (!tight) {
                    out.push_back('\n');
                }
            }

            std::string marker = ordered ? std::to_string(number) + (variant != 0 ? ") " : ". ")
                                         : std::string(variant != 0 ? "* " : "- ");
            // Only the first number is honoured on reparse, so repeating the ceiling
            // changes nothing about the parsed result.
            number = std::min(number + 1, kMaxListStart);
            out += render_list_item(child, marker, indent, task || child.type == "taskItem");
            item_index++;
        });
        return out;
    }

    // Whether two adjacent blocks inside a list item need a blank line between
    // them to reparse as separate blocks. Blank lines are avoided where markdown
    // does not require them, so tight lists stay tight.
    static bool needs_blank_between(BlockKind prev, BlockKind next) {
        if (prev == BlockKind::TextBlock || next == BlockKind::TextBlock) {
            return true;
        }
        if (prev == BlockKind::Html || (prev == BlockKind::Table && next == BlockKind::TagLine)) {
            return true;
        }
        if (prev == BlockKind::TagLine || next == BlockKind::TagLine) {
            return false;
        }
        if (next == BlockKind::Paragraph || next == BlockKind::Table || next == BlockKind::Html) {
            return true;
        }
        return prev == BlockKind::Blockquote && next == BlockKind::Blockquote;
    }

    std::string render_list_item(const Node& node, const std::string& marker, int indent, bool task) {
        std::vector<BlockPiece> pieces = block_pieces(node, 0, true);
        if (task) {
            // A checkbox-only line in a loose list reads as an empty paragraph.
            // Keeping it as a leading piece would add a line when the item is written again.
            auto first = std::find_if(pieces.begin(), pieces.end(), [](const BlockPiece& piece) {
                return piece.kind != BlockKind::Paragraph || !piece.text.empty();
            });
            pieces.erase(pieces.begin(), first);
        }
        BlockKind first_kind = pieces.empty() ? BlockKind::Other : pieces.front().kind;
        std::string body = join_block_pieces(std::move(pieces), true);
        std::vector<std::string> lines = split_lines(body);
        std::string out = repeat(' ', static_cast<std::size_t>(indent)) + marker;
        if (task) {
            out += attr_bool(node.attrs, "checked", false) ? "[x]" : "[ ]";
        }
        if (lines.empty() || (lines.size() == 1 && lines[0].empty())) {
            if (task) {
                out.push_back(' ');
            }
            return out;
        }

        // The checkbox belongs to the content; it does not widen the list marker's continuation indent.
        std::string continuation = repeat(' ', static_cast<std::size_t>(indent + static_cast<int>(marker.size())));
        if (task) {
            if (first_kind == BlockKind::Paragraph || first_kind == BlockKind::TextBlock ||
                first_kind == BlockKind::Inline) {
                out.push_back(' ');
            } else {
                out.push_back('\n');
                out += continuation;
            }
        }
        out += lines[0];
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
        return render_fenced_code(plain_text(node), code_info(node.attrs).value);
    }

    std::string render_fenced_code(std::string code, std::string language) {
        // A backtick inside the info string closes a backtick fence,
        // so those switch to tildes — which have no such restriction, and lose nothing.
        // The parser reaches this too: "~~~py`x" is a valid tilde fence,
        // and its info string comes back out through here.
        char fence_char = language.find('`') == std::string::npos ? '`' : '~';
        std::size_t fence_len = std::max<std::size_t>(3, max_run(code, fence_char) + 1);
        std::string fence(fence_len, fence_char);

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
                blocks.push_back(render_inlines(child, InlineContext::TableCell));
            } else if (type == "text" || type == "hardBreak" || type == "image" || type == "htmlInline") {
                blocks.push_back(render_inline(child, InlineContext::TableCell));
            } else {
                const NodeSpec* spec = declared_nodes_ ? declared_form(child) : nullptr;
                blocks.push_back(render_block(child, 0, spec, 0, InlineContext::TableCell));
            }
        });
        rendered = join(blocks, "<br>");
        std::replace(rendered.begin(), rendered.end(), '\n', ' ');
        return rendered;
    }

    // Render one inline node without applying its marks. Marks are emitted by
    // emit_runs(), which keeps marks shared between consecutive runs open
    // across the boundary.
    std::string render_inline_content(const Node& node, InlineContext ctx, bool in_code) {
        const std::string& type = node.type;
        if (type == "text") {
            if (ctx == InlineContext::Heading && node.text.find('\n') != std::string::npos) {
                // ATX headings are single-line; literal newlines (e.g. carried
                // over from setext input) demote to spaces.
                std::string flattened = node.text;
                std::replace(flattened.begin(), flattened.end(), '\n', ' ');
                return in_code ? flattened : escape_text(flattened, false);
            }
            return in_code ? node.text : escape_text(node.text, ctx == InlineContext::TableCell);
        }
        if (type == "hardBreak") {
            if (ctx == InlineContext::TableCell) {
                return "<br>";
            }
            if (ctx == InlineContext::Heading) {
                return " ";
            }
            return "  \n";
        }
        if (type == "image") {
            std::string src = attr_string(node.attrs, "src");
            std::string alt = attr_string(node.attrs, "alt", plain_text(node));
            std::string title = attr_string(node.attrs, "title");
            return "![" + escape_text(alt, ctx == InlineContext::TableCell) + "](" + escape_link_destination(src) +
                   (title.empty() ? "" : " \"" + escape_title(title) + "\"") + ")";
        }
        if (type == "htmlInline") {
            return attr_string(node.attrs, "html", plain_text(node));
        }
        if (declared_nodes_) {
            const NodeSpec& spec = *schema_.node(type);
            if (!spec.core) {
                if (spec.math == MathMode::Inline) {
                    const AttrValue* body = carrier_body(spec, node.attrs);
                    if (body != nullptr &&
                        inline_math_body_allowed(body->string_value, ctx == InlineContext::TableCell,
                                                 !node.marks.empty())) {
                        return math_token(node, spec);
                    }
                }
                return open_node_tag(spec, node.attrs);
            }
        }
        return render_inlines(node, ctx);
    }

    const NodeSpec* declared_inline_spec(const Node& node) const {
        const std::string& type = node.type;
        if (type == "text" || type == "hardBreak" || type == "image" || type == "htmlInline") {
            return nullptr;
        }
        const NodeSpec& spec = *schema_.node(type);
        return !spec.core && (spec.shape == Shape::InlineAtom || spec.shape == Shape::InlineContainer)
                   ? &spec : nullptr;
    }

    bool declared_inline_atom(const Node& node) const {
        const NodeSpec* spec = declared_inline_spec(node);
        return spec != nullptr && spec->shape == Shape::InlineAtom;
    }

    std::string render_inlines(const Node& node, InlineContext ctx = InlineContext::Default) {
        if (node.content.empty() && node.type == "text") {
            return render_inline(node, ctx);
        }

        if (inline_containers_) {
            return render_inline_segments(node.content, ctx);
        }
        return render_inline_segment(node.content, 0, node.content.size(), ctx);
    }

    std::string render_inline_segment(const std::vector<std::size_t>& content, std::size_t begin, std::size_t end,
                                      InlineContext ctx) {
        std::vector<InlineRun> runs = build_runs(content, begin, end, ctx);
        expel_boundary_whitespace(runs);
        return emit_runs(runs, schema_);
    }

    std::string render_inline_segments(const std::vector<std::size_t>& content, InlineContext ctx) {
        std::string out;
        std::size_t begin = 0;
        for (std::size_t i = 0; i < content.size(); ++i) {
            const Node& child = document_.node(content[i]);
            const NodeSpec* spec = declared_inline_spec(child);
            if (spec == nullptr || spec->shape != Shape::InlineContainer) {
                continue;
            }
            // Container tags close the surrounding marks before the inner inline sequence starts.
            out += render_inline_segment(content, begin, i, ctx);
            out += open_node_tag(*spec, child.attrs) + render_inlines(child, ctx) + close_node_tag(*spec);
            begin = i + 1;
        }
        out += render_inline_segment(content, begin, content.size(), ctx);
        return out;
    }

    std::vector<InlineRun> build_runs(const std::vector<std::size_t>& content, std::size_t begin, std::size_t end,
                                      InlineContext ctx) {
        std::vector<InlineRun> runs;
        std::size_t i = begin;
        while (i < end) {
            const Node& first = document_.node(content[i]);
            bool in_code = has_mark(first.marks, "code");
            bool code_atom = in_code && declared_nodes_ && declared_inline_atom(first);
            in_code = in_code && !code_atom;
            std::size_t group_end = code_atom ? i + 1 : end;
            std::string group;
            std::size_t j = i;
            while (j < group_end) {
                const Node& child = document_.node(content[j]);
                if (!(child.marks == first.marks)) {
                    break;
                }
                if (in_code && declared_nodes_ && declared_inline_atom(child)) {
                    break;
                }
                group += render_inline_content(child, ctx, in_code);
                ++j;
            }

            InlineRun run;
            for (const Mark& mark : first.marks) {
                if (mark.type != "code") {
                    run.marks.push_back(mark);
                }
            }
            if (extended_) {
                // Tag marks must enclose delimiters before whitespace is expelled,
                // so the whitespace keeps its tag marks and emphasis can still flank text.
                order_tag_marks(run.marks, schema_);
            }
            run.content = in_code ? code_span(group) : std::move(group);
            runs.push_back(std::move(run));
            i = j;
        }
        return runs;
    }

    std::string render_inline(const Node& node, InlineContext ctx = InlineContext::Default) {
        const NodeSpec* spec = declared_nodes_ ? declared_inline_spec(node) : nullptr;
        if (spec != nullptr && spec->shape == Shape::InlineContainer) {
            return open_node_tag(*spec, node.attrs) + render_inlines(node, ctx) + close_node_tag(*spec);
        }
        bool in_code = has_mark(node.marks, "code");
        bool skip_code = in_code;
        if (spec != nullptr) {
            in_code = false;
        }
        std::string rendered = render_inline_content(node, ctx, in_code);
        std::vector<Mark> ordered;
        const std::vector<Mark>* marks = &node.marks;
        if (extended_) {
            ordered = node.marks;
            order_tag_marks(ordered, schema_);
            marks = &ordered;
        }
        return apply_marks(in_code ? code_span(rendered) : std::move(rendered), *marks, schema_, skip_code);
    }

    std::string plain_text(const Node& node) {
        const std::string& type = node.type;
        if (type == "text") {
            return node.text;
        }
        if (type == "hardBreak") {
            return "\n";
        }
        // The attr is the payload when the key is present, even if its value is empty.
        // When it is absent, fall through to the children:
        // from_dict accepts and stores content on these nodes,
        // and returning "" here would drop it — the silent loss the closed schema exists to prevent.
        // Callers use this as the fallback for the very same attr (see the htmlBlock and image
        // branches above), so returning the attr unconditionally would just recurse to "".
        if (type == "htmlInline" || type == "htmlBlock") {
            if (find_attr(node.attrs, "html") != nullptr) {
                return attr_string(node.attrs, "html");
            }
        } else if (type == "image") {
            if (find_attr(node.attrs, "alt") != nullptr) {
                return attr_string(node.attrs, "alt");
            }
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
