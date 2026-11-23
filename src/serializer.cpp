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

bool ascii_alnum(char ch) {
    return (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z');
}

bool autolink_space(std::string_view value, std::size_t at) {
    unsigned char ch = value[at];
    if (ch < 0x80) {
        return ch == ' ' || (ch >= '\t' && ch <= '\r');
    }
    if (ch == 0xc2) {
        return value.substr(at, 2) == u8"\u00a0";
    }
    std::string_view bytes = value.substr(at, 3);
    return bytes == u8"\u1680" || (bytes >= u8"\u2000" && bytes <= u8"\u200a") ||
           bytes == u8"\u202f" || bytes == u8"\u205f" || bytes == u8"\u3000";
}

bool autolink_left_boundary(std::string_view value, std::size_t begin) {
    if (begin == 0 || std::string_view("({[").find(value[begin - 1]) != std::string_view::npos) {
        return true;
    }
    std::size_t previous = begin - 1;
    while (previous > 0 && (static_cast<unsigned char>(value[previous]) & 0xc0) == 0x80) {
        --previous;
    }
    return autolink_space(value, previous);
}

bool autolink_candidate(std::string_view value, std::size_t trigger) {
    std::size_t begin = trigger;
    std::size_t end = trigger + 1;
    bool email = value[trigger] == '@';
    if (email) {
        if (begin == 0 || value.size() - trigger <= 3 ||
            !ascii_alnum(value[begin - 1]) || !ascii_alnum(value[end])) {
            return false;
        }
        while (begin > 0) {
            if (ascii_alnum(value[begin - 1])) {
                --begin;
            } else if (begin >= 2 && ascii_alnum(value[begin - 2]) && ascii_alnum(value[begin]) &&
                       std::string_view(".-_+").find(value[begin - 1]) != std::string_view::npos) {
                --begin;
            } else {
                break;
            }
        }
    } else if (value[trigger] == ':') {
        if (value.substr(end, 2) != "//") {
            return false;
        }
        for (std::string_view scheme : {"http", "https", "ftp"}) {
            if (trigger >= scheme.size() && value.substr(trigger - scheme.size(), scheme.size()) == scheme) {
                begin = trigger - scheme.size();
                break;
            }
        }
        if (begin == trigger) {
            return false;
        }
        end += 2;
    } else {
        if (trigger < 3 || value.substr(trigger - 3, 3) != "www") {
            return false;
        }
        begin = trigger - 3;
    }
    if (!autolink_left_boundary(value, begin)) {
        return false;
    }

    // MD4C's host, path and query rules apply to the escaped bytes.
    // Escaped parentheses and '#' stop the scan before a query bracket or fragment.
    struct Part {
        char prefix;
        char separator;
        std::string_view inside;
        std::string_view anywhere;
        std::size_t minimum;
    };
    constexpr Part parts[] = {
        {'\0', '.', ".-_", "", 2},
        {'/', '/', "/._", "+-", 0},
        {'?', '&', "&.-+_=", "", 1},
    };
    for (const Part& part : parts) {
        auto accepts = [&](char ch) {
            return ascii_alnum(ch) || part.anywhere.find(ch) != std::string_view::npos;
        };
        if (part.prefix != '\0') {
            if (end == value.size() || value[end] != part.prefix ||
                (part.minimum != 0 && (end + 1 == value.size() || !ascii_alnum(value[end + 1])))) {
                continue;
            }
            ++end;
        }
        std::size_t components = 0;
        std::size_t length = 0;
        while (end < value.size()) {
            char ch = value[end];
            if (accepts(ch)) {
                components = std::max<std::size_t>(1, components);
                ++length;
            } else if (length != 0 && ch == part.separator && end + 1 < value.size() && accepts(value[end + 1])) {
                ++components;
                length = 0;
            } else if (part.inside.find(ch) != std::string_view::npos && ascii_alnum(value[end - 1]) &&
                       end + 1 < value.size() && ascii_alnum(value[end + 1])) {
                ++length;
            } else {
                break;
            }
            ++end;
        }
        if (part.prefix == '/' && end < value.size() && value[end] == '/') {
            ++end;
        }
        if (components < part.minimum) {
            return false;
        }
        if (email) {
            break;
        }
    }
    return end == value.size() || autolink_space(value, end) ||
           std::string_view(")}].!?,;").find(value[end]) != std::string_view::npos;
}

void escape_autolinks(std::string& run, std::size_t start = 0) {
    std::string_view value = std::string_view(run).substr(start);
    std::size_t www = value.find("www.");
    if (www != std::string_view::npos) {
        www += 3;
    }
    std::size_t trigger = std::min({value.find('@'), value.find("://"), www});
    if (trigger == std::string_view::npos) {
        return;
    }

    std::string escaped;
    std::size_t begin = 0;
    for (; trigger != std::string_view::npos; trigger = value.find_first_of("@:.", trigger + 1)) {
        if (autolink_candidate(value, trigger)) {
            if (escaped.empty()) {
                escaped.reserve(value.size() + 1);
            }
            escaped.append(value.substr(begin, trigger - begin));
            escaped.push_back('\\');
            begin = trigger;
        }
    }
    if (!escaped.empty()) {
        escaped.append(value.substr(begin));
        run.replace(start, std::string::npos, escaped);
    }
}

// Stored text has no NUL, and the marker's nondigit after adjacent NULs keeps it distinct from math tokens through escaping.
constexpr std::string_view kHtmlLineMarker("\0\0h\0", 4);

// Escape block starts on paragraph lines,
// including list markers, quote markers, setext underlines and table delimiter rows.
std::string escape_line_starts(std::string value) {
    std::string out;
    std::size_t copied = 0;
    std::size_t marker = value.find(kHtmlLineMarker);
    auto copy_until = [&](std::size_t end) {
        while (marker < end) {
            out.append(value, copied, marker - copied);
            copied = marker + kHtmlLineMarker.size();
            marker = value.find(kHtmlLineMarker, copied);
        }
        out.append(value, copied, end - copied);
        copied = end;
    };
    std::size_t next_line = 0;
    for (std::size_t li = 0; next_line < value.size(); ++li) {
        std::size_t line_begin = next_line;
        std::size_t newline = value.find('\n', line_begin);
        next_line = newline == std::string::npos ? value.size() : newline + 1;
        std::string_view line = std::string_view(value).substr(line_begin, newline - line_begin);
        if (line.substr(0, kHtmlLineMarker.size()) == kHtmlLineMarker) {
            continue;
        }
        std::size_t start = 0;
        while (start < line.size() && start < 3 && line[start] == ' ') {
            ++start;
        }
        bool table_delimiter = false;
        if (li == 1) {
            std::size_t first = line.find_first_not_of(" \t");
            if (first != std::string_view::npos && (line[first] == '|' || line[first] == ':')) {
                start = first;
                table_delimiter = true;
            }
        }
        std::size_t escape = std::string_view::npos;
        if (start < line.size()) {
            char first = line[start];
            if (table_delimiter || first == '-' || first == '+' || first == '>') {
                escape = start;
            } else if (first == '=') {
                if (line.find_first_not_of("= \t", start) == std::string_view::npos) {
                    escape = start;
                }
            } else if (first >= '0' && first <= '9') {
                std::size_t digits_end = line.find_first_not_of("0123456789", start);
                if (digits_end != std::string_view::npos && digits_end - start <= 9 && line[digits_end] == '.' &&
                    (digits_end + 1 == line.size() || line[digits_end + 1] == ' ' ||
                     line[digits_end + 1] == '\t')) {
                    escape = digits_end;
                }
            }
        }
        if (escape != std::string_view::npos) {
            if (out.empty()) {
                out.reserve(value.size() + 1);
            }
            copy_until(line_begin + escape);
            out.push_back('\\');
        }
    }
    if (out.empty()) {
        if (marker == std::string::npos) {
            return value;
        }
        out.reserve(value.size());
    }
    copy_until(value.size());
    return out;
}

std::string escape_link_destination(std::string_view value, bool has_title) {
    bool needs_angle = (value.empty() && has_title) || value.find_first_of(" \t()") != std::string_view::npos;
    std::string out;
    out.reserve(value.size());
    if (needs_angle) {
        out.push_back('<');
    }
    for (char ch : value) {
        if (ch == '\\' || ch == '`' || (needs_angle && (ch == '<' || ch == '>'))) {
            out.push_back('\\');
        }
        out.push_back(ch);
    }
    if (needs_angle) {
        out.push_back('>');
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
                                  value.front() == ' ' || value.back() == ' ') &&
               value.find_first_not_of(' ') != std::string_view::npos;
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
            if (schema.has_link_tag() && uses_tag_form(*it, *schema.mark(it->type))) {
                rendered = open_tag(schema, *it) + rendered + close_tag(schema, *it);
                continue;
            }
            std::string href = mark_attr_string(*it, "href");
            std::string title = mark_attr_string(*it, "title");
            rendered = "[" + rendered + "](" + escape_link_destination(href, !title.empty()) +
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

// Adjacent lists of the same family would merge on reparse if they used the same marker,
// so sibling loops alternate the marker between consecutive same-family lists.
// Spelled roots also use "+" when both other bullet markers are occupied by neighbours.
enum class ListFamily { None, Bullet, Ordered };

enum class BlockKind {
    Paragraph, TextBlock, Image, Inline, TagLine, Html, Blockquote, Table, Heading, FencedCode,
    NonInterruptingList, Other
};

struct BlockPiece {
    BlockPiece(std::string&& text, BlockKind kind, ListFamily family)
        : text(std::move(text)), kind(kind), family(family) {}

    std::string text;
    BlockKind kind;
    ListFamily family;
};

struct BlockOrigin {
    const SpellingPiece* source;
    bool remembered;
};

struct SpelledBlocks {
    std::vector<BlockPiece> pieces;
    std::vector<BlockOrigin> origins;
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

int remembered_list_marker(std::string_view text, ListFamily family) {
    std::size_t pos = text.find_first_not_of(" \t");
    if (pos == std::string_view::npos) {
        return -1;
    }
    int variant = -1;
    if (family == ListFamily::Bullet) {
        std::size_t marker = std::string_view("-*+").find(text[pos]);
        if (marker != std::string_view::npos) {
            variant = static_cast<int>(marker);
            ++pos;
        }
    } else if (family == ListFamily::Ordered) {
        std::size_t begin = pos;
        while (pos < text.size() && text[pos] >= '0' && text[pos] <= '9') {
            ++pos;
        }
        if (pos > begin && pos < text.size() && (text[pos] == '.' || text[pos] == ')')) {
            variant = text[pos++] == '.' ? 0 : 1;
        }
    }
    return pos == text.size() || text[pos] == ' ' || text[pos] == '\t' || text[pos] == '\r' || text[pos] == '\n'
               ? variant : -1;
}

int available_list_variant(ListFamily family, int left, int right = -1) {
    int variant = 0;
    int last = family == ListFamily::Bullet ? 2 : 1;
    while (variant < last && (variant == left || variant == right)) {
        ++variant;
    }
    return variant;
}

bool gap_has_blank_line(std::string_view gap) {
    unsigned lines = 0;
    for (std::size_t i = 0; i < gap.size(); ++i) {
        if (gap[i] == '\r') {
            ++lines;
            if (i + 1 < gap.size() && gap[i + 1] == '\n') {
                ++i;
            }
        } else if (gap[i] == '\n') {
            ++lines;
        }
        if (lines == 2) {
            return true;
        }
    }
    return false;
}

std::string_view spelled_gap(const Spelling& spelling, const BlockOrigin& previous, const BlockOrigin* next) {
    std::string_view gap = spelling.view(previous.source->gap);
    if (next == nullptr) {
        return previous.remembered ? gap : std::string_view {};
    }
    bool original_neighbours = previous.remembered && next->remembered &&
                               previous.source->gap.end == next->source->text->begin;
    return previous.source != next->source && (gap_has_blank_line(gap) || original_neighbours)
               ? gap : std::string_view("\n\n");
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
        if (schema.has_link_tag() && uses_tag_form(mark, *schema.mark(mark.type))) {
            return open_tag(schema, mark);
        }
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
        if (schema.has_link_tag() && uses_tag_form(mark, *schema.mark(mark.type))) {
            return close_tag(schema, mark);
        }
        std::string href = mark_attr_string(mark, "href");
        std::string title = mark_attr_string(mark, "title");
        return "](" + escape_link_destination(href, !title.empty()) +
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
        : document_(document), schema_(document.schema()),
          extended_(schema_.has_declared_marks() || schema_.has_link_tag()),
          node_forms_(schema_.has_declared_nodes() || schema_.has_core_attrs()),
          math_(schema_.has_math()) {}

    std::string render(bool canonical) {
        if (document_.root().type != "doc") {
            throw InvalidNodeError("invalid_root", "type", "root node must have type 'doc'", "");
        }
        const Spelling* spelling = !canonical && document_.spelling() ? &*document_.spelling() : nullptr;
        std::string rendered = render_doc(document_.root(), spelling);
        if (!math_tokens_.empty()) {
            return resolve_math(std::move(rendered));
        }
        return rendered;
    }

    std::optional<StoredSpelling> dump_spelling() {
        if (!document_.spelling()) {
            return std::nullopt;
        }
        const Spelling& spelling = *document_.spelling();
        SpelledBlocks blocks = spelled_blocks(document_.root(), spelling);
        StoredSpelling stored;
        stored.head = spelling.view(spelling.head);
        stored.items.reserve(spelling.items.size());
        for (const SpellingPiece& source : spelling.items) {
            stored.items.push_back({std::nullopt, {}, source.has_node});
        }
        for (std::size_t i = 0; i < blocks.pieces.size(); ++i) {
            const BlockOrigin& origin = blocks.origins[i];
            StoredPiece& item = stored.items[origin.source - spelling.items.data()];
            if (origin.remembered) {
                item.text = std::move(blocks.pieces[i].text);
            }
            const BlockOrigin* next = i + 1 < blocks.origins.size() ? &blocks.origins[i + 1] : nullptr;
            if (next == nullptr || next->source != origin.source) {
                item.sep = spelled_gap(spelling, origin, next);
            }
        }
        return stored;
    }

private:
    const Document& document_;
    const Schema& schema_;
    bool extended_;
    bool node_forms_;
    bool math_;
    bool mark_html_line_starts_ = false;
    std::vector<MathToken> math_tokens_;

    std::string escape_text(std::string_view value, bool table_cell) {
        std::string escaped = escape_inline(value, table_cell);
        if (math_) {
            escaped = escape_dollars(std::move(escaped));
        }
        return escaped;
    }

    bool has_markdown_link(const std::vector<Mark>& marks) const {
        return std::any_of(marks.begin(), marks.end(), [&](const Mark& mark) {
            return mark.type == "link" && (!schema_.has_link_tag() || !uses_tag_form(mark, *schema_.mark(mark.type)));
        });
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
        // Remembered source contains no NUL, so this pass replaces only markers emitted for generated text.
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

    SpelledBlocks spelled_blocks(const Node& node, const Spelling& spelling) {
        SpelledBlocks blocks;
        blocks.origins.reserve(spelling.items.size());
        int prev_variant = 0;
        collect_block_children(node, nullptr, 0, false, blocks.pieces, prev_variant, &spelling, &blocks.origins);
        return blocks;
    }

    std::string render_doc(const Node& node, const Spelling* spelling = nullptr) {
        if (spelling == nullptr) {
            return render_blocks(node, 0);
        }
        SpelledBlocks blocks = spelled_blocks(node, *spelling);
        std::vector<BlockPiece>& pieces = blocks.pieces;
        const std::vector<BlockOrigin>& origins = blocks.origins;
        if (pieces.empty()) {
            return std::string(spelling->view(spelling->head));
        }
        std::string out = std::move(pieces.front().text);
        out.insert(0, spelling->view(spelling->head));
        std::size_t size = out.size();
        for (std::size_t i = 1; i < pieces.size(); ++i) {
            size += pieces[i].text.size();
        }
        size += 2 * (pieces.size() - 1);
        out.reserve(size);
        for (std::size_t i = 1; i < pieces.size(); ++i) {
            out += spelled_gap(*spelling, origins[i - 1], &origins[i]);
            out += pieces[i].text;
        }
        out += spelled_gap(*spelling, origins.back(), nullptr);
        return out;
    }

    std::string render_blocks(const Node& node, int indent) {
        return join_block_pieces(block_pieces(node, indent, false), false);
    }

    static bool omits_empty_paragraph(const Node& parent) {
        std::string_view type = parent.type;
        return parent.content.size() == 1 &&
               (type == "listItem" || type == "taskItem" || type == "tableCell" || type == "tableHeader" ||
                type == "blockquote");
    }

    const NodeSpec* declared_form(const Node& node, const Node* parent = nullptr) const {
        const NodeSpec& spec = *schema_.node(node.type);
        bool tag_empty_paragraph = parent != nullptr && node.content.empty() && node.type == "paragraph" &&
                                   !spec.tag.empty() && !omits_empty_paragraph(*parent);
        return !spec.core || tag_empty_paragraph || uses_tag_form(document_, node, spec) ? &spec : nullptr;
    }

    BlockKind block_kind(const Node& node, const NodeSpec* spec) const {
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
            return schema_.block_image() ? BlockKind::Image : BlockKind::Inline;
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
        if (type == "orderedList" && attr_int(node.attrs, "start", 1) != 1) {
            return BlockKind::NonInterruptingList;
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
        std::string tag = closing ? close_node_tag(spec, node.attrs) : open_node_tag(spec, node.attrs);
        pieces.emplace_back(add_indent(std::move(tag), indent), BlockKind::TagLine, ListFamily::None);
        prev_variant = 0;
    }

    void collect_block_children(const Node& node, const NodeSpec* container, int indent, bool list_item,
                                std::vector<BlockPiece>& pieces, int& prev_variant,
                                const Spelling* spelling = nullptr,
                                std::vector<BlockOrigin>* origins = nullptr) {
        pieces.reserve(node.content.size());
        ContentModel inherited = container != nullptr && container->core ? container->allow : ContentModel::None;
        if (container != nullptr && !container->implicit) {
            append_container_tag(node, *container, indent, false, pieces, prev_variant);
        }
        const Node* generated_list = nullptr;
        int pending_replacement = 0;
        auto collect_child = [&](const Node& child) {
            const NodeSpec* spec = nullptr;
            if (node_forms_) {
                bool follows_parent = false;
                switch (inherited) {
                    case ContentModel::ListItems:
                    case ContentModel::OrderedListItems:
                    case ContentModel::TaskItems:
                        follows_parent = child.type == "listItem" || child.type == "taskItem";
                        break;
                    case ContentModel::Rows:
                        follows_parent = child.type == "tableRow";
                        break;
                    case ContentModel::Cells:
                        follows_parent = child.type == "tableCell" || child.type == "tableHeader";
                        break;
                    default:
                        break;
                }
                spec = follows_parent ? schema_.node(child.type) : declared_form(child, &node);
            }
            if (spec != nullptr && spec->shape == Shape::BlockContainer) {
                collect_block_children(child, spec, indent, list_item, pieces, prev_variant);
                return;
            }

            ListFamily family = list_family(child.type);
            bool follows_list = family != ListFamily::None && !pieces.empty() && pieces.back().family == family;
            int variant = follows_list ? available_list_variant(family, prev_variant) : 0;
            std::string rendered = render_block(child, indent, spec, variant, InlineContext::Default, list_item);
            if (!list_item) {
                rstrip_newlines(rendered);
            }
            if ((!list_item || container != nullptr) && rendered.empty()) {
                return;
            }
            if (family != ListFamily::None && spelling != nullptr) {
                pending_replacement = available_list_variant(family, follows_list ? prev_variant : -1, variant);
                if (pending_replacement != variant && (!follows_list || pending_replacement != prev_variant)) {
                    generated_list = &child;
                }
            }
            pieces.emplace_back(std::move(rendered), list_item ? block_kind(child, spec) : BlockKind::Other, family);
            prev_variant = variant;
        };
        if (spelling != nullptr) {
            std::size_t child_index = 0;
            const Node* pending_list = nullptr;
            for (const SpellingPiece& source : spelling->items) {
                const Node* child = source.has_node ? &document_.node(node.content[child_index++]) : nullptr;
                std::size_t begin = pieces.size();
                bool remembered = false;
                generated_list = nullptr;
                if (source.text) {
                    ListFamily family = child != nullptr ? list_family(child->type) : ListFamily::None;
                    std::string_view text = spelling->view(*source.text);
                    int variant = remembered_list_marker(text, family);
                    remembered = true;
                    if (variant >= 0 && !pieces.empty() && pieces.back().family == family &&
                        variant == prev_variant) {
                        if (pending_list != nullptr) {
                            // Re-render the pending generated list to avoid the next remembered list's marker.
                            pieces.back().text = render_block(*pending_list, indent, nullptr, pending_replacement,
                                                              InlineContext::Default, list_item);
                            rstrip_newlines(pieces.back().text);
                        } else {
                            collect_child(*child);
                            remembered = false;
                        }
                    }
                    pending_list = nullptr;
                    if (remembered) {
                        pieces.emplace_back(std::string(text), BlockKind::Other,
                                            variant >= 0 ? family : ListFamily::None);
                        if (variant >= 0) {
                            prev_variant = variant;
                        }
                    }
                } else if (child != nullptr) {
                    collect_child(*child);
                }
                origins->resize(pieces.size(), {&source, remembered});
                if (pieces.size() == begin) {
                    continue;
                }
                pending_list = generated_list;
            }
        } else {
            for_each_child(node, collect_child);
        }
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

    std::string render_textblock(const Node& node, InlineContext ctx, const NodeSpec* spec = nullptr) {
        mark_html_line_starts_ = true;
        std::string rendered = render_inlines(node, ctx);
        mark_html_line_starts_ = false;
        if (spec != nullptr) {
            rendered = open_node_tag(*spec, node.attrs) + rendered + close_node_tag(*spec, node.attrs);
        }
        return escape_line_starts(std::move(rendered));
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
            return add_indent(render_textblock(node, ctx, &spec), indent);
        }
        if (spec.shape == Shape::BlockAtom) {
            if (const AttrValue* body = fence_body(spec, node.attrs, ctx == InlineContext::TableCell)) {
                return add_indent(render_fenced_code(body->string_value, spec.fence), indent);
            }
            return add_indent(open_node_tag(spec, node.attrs), indent);
        }
        return add_indent(render_inline(node, ctx), indent);
    }

    std::string render_block(const Node& node, int indent, const NodeSpec* spec, int list_variant = 0,
                             InlineContext ctx = InlineContext::Default, bool list_item = false) {
        if (spec != nullptr) {
            return render_declared(node, *spec, indent, ctx);
        }
        const std::string& type = node.type;
        if (type == "doc") {
            return render_doc(node);
        }
        if (type == "paragraph") {
            return add_indent(render_textblock(node, InlineContext::Default), indent);
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
            // Underscores cannot become a setext underline or combine with a bullet marker into one rule.
            return add_indent(list_item ? "___" : "---", indent);
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
                                         : std::string(variant == 2 ? "+ " : variant != 0 ? "* " : "- ");
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

    std::string render_list_item(const Node& node, const std::string& marker, int indent, bool task) {
        std::vector<BlockPiece> pieces = block_pieces(node, 0, true);
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
                first_kind == BlockKind::Image || first_kind == BlockKind::Inline) {
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

    std::string render_fenced_code(std::string code, std::string info) {
        // A backtick in the info string requires a tilde fence.
        char fence_char = info.find('`') == std::string::npos ? '`' : '~';
        std::size_t fence_len = std::max<std::size_t>(3, max_run(code, fence_char) + 1);
        std::string fence(fence_len, fence_char);

        std::string out;
        out.reserve(2 * fence_len + info.size() + code.size() + 2);
        out += fence;
        // A leading tilde in the info string would extend a tilde fence.
        if (!info.empty() && info.front() == fence_char) {
            out.push_back(' ');
        }
        // MD4C decodes backslash escapes in fence attrs.
        for (char ch : info) {
            if (ch == '\\') {
                out.push_back('\\');
            }
            out.push_back(ch);
        }
        out.push_back('\n');
        out += code;
        out.push_back('\n');
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
                const NodeSpec* spec = node_forms_ ? declared_form(child, &cell) : nullptr;
                blocks.push_back(spec != nullptr ? render_declared(child, *spec, 0, InlineContext::TableCell)
                                                 : render_inlines(child, InlineContext::TableCell));
            } else if (type == "text" || type == "hardBreak" || type == "image" || type == "htmlInline") {
                blocks.push_back(render_inline(child, InlineContext::TableCell));
            } else {
                const NodeSpec* spec = node_forms_ ? declared_form(child) : nullptr;
                blocks.push_back(render_block(child, 0, spec, 0, InlineContext::TableCell));
            }
        });
        rendered = join(blocks, "<br>");
        std::replace(rendered.begin(), rendered.end(), '\n', ' ');
        return rendered;
    }

    // Render one inline node without applying its marks.
    // emit_runs() keeps marks shared between consecutive runs open across the boundary.
    std::string render_inline_content(const Node& node, InlineContext ctx, bool in_code,
                                      const std::vector<Mark>& enclosing) {
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
            return "\\\n";
        }
        if (type == "image") {
            if (node_forms_) {
                if (const NodeSpec* spec = declared_form(node)) {
                    return open_node_tag(*spec, node.attrs);
                }
            }
            std::string src = attr_string(node.attrs, "src");
            std::string alt = attr_string(node.attrs, "alt", plain_text(node));
            std::string title = attr_string(node.attrs, "title");
            return "![" + escape_text(alt, ctx == InlineContext::TableCell) + "](" +
                   escape_link_destination(src, !title.empty()) +
                   (title.empty() ? "" : " \"" + escape_title(title) + "\"") + ")";
        }
        if (type == "htmlInline") {
            std::string html = attr_string(node.attrs, "html", plain_text(node));
            std::size_t newline = mark_html_line_starts_ ? html.find('\n') : std::string::npos;
            if (newline == std::string::npos || newline + 1 == html.size()) {
                return html;
            }
            std::string marked;
            marked.reserve(html.size() + kHtmlLineMarker.size());
            std::size_t start = 0;
            do {
                marked.append(html, start, newline + 1 - start);
                marked += kHtmlLineMarker;
                start = newline + 1;
                newline = html.find('\n', start);
            } while (newline != std::string::npos && newline + 1 < html.size());
            marked.append(html, start, std::string::npos);
            return marked;
        }
        if (node_forms_) {
            const NodeSpec& spec = *schema_.node(type);
            if (!spec.core) {
                if (spec.math == MathMode::Inline) {
                    const AttrValue* body = carrier_body(spec, node.attrs);
                    if (body != nullptr &&
                        inline_math_body_allowed(body->string_value, ctx == InlineContext::TableCell,
                                                 !node.marks.empty() || !enclosing.empty())) {
                        return math_token(node, spec);
                    }
                }
                std::string rendered = open_node_tag(spec, node.attrs);
                if (spec.shape == Shape::InlineContainer) {
                    std::vector<Mark> inner = enclosing;
                    for (const Mark& mark : node.marks) {
                        if (mark.type != "code" && !uses_tag_form(mark, *schema_.mark(mark.type)) &&
                            std::find(inner.begin(), inner.end(), mark) == inner.end()) {
                            inner.push_back(mark);
                        }
                    }
                    rendered += render_inlines(node, ctx, inner) + close_node_tag(spec, node.attrs);
                }
                return rendered;
            }
        }
        return render_inlines(node, ctx, enclosing);
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

    std::string render_inlines(const Node& node, InlineContext ctx = InlineContext::Default,
                               const std::vector<Mark>& enclosing = {}) {
        if (node.content.empty() && node.type == "text") {
            return render_inline(node, ctx);
        }

        std::vector<InlineRun> runs = build_runs(node.content, ctx, enclosing);
        expel_boundary_whitespace(runs);
        return emit_runs(runs, schema_);
    }

    std::vector<InlineRun> build_runs(const std::vector<std::size_t>& content, InlineContext ctx,
                                      const std::vector<Mark>& enclosing) {
        std::vector<InlineRun> runs;
        auto without_enclosing = [&](const std::vector<Mark>& marks) {
            std::vector<Mark> filtered;
            for (const Mark& mark : marks) {
                if (std::find(enclosing.begin(), enclosing.end(), mark) == enclosing.end()) {
                    filtered.push_back(mark);
                }
            }
            return filtered;
        };
        std::size_t i = 0;
        while (i < content.size()) {
            const Node& first = document_.node(content[i]);
            std::vector<Mark> filtered;
            if (!enclosing.empty()) {
                filtered = without_enclosing(first.marks);
            }
            const std::vector<Mark>& marks = enclosing.empty() ? first.marks : filtered;
            bool in_code = has_mark(marks, "code");
            bool code_node = in_code && node_forms_ && declared_inline_spec(first) != nullptr;
            in_code = in_code && !code_node;
            bool escape_links = !in_code && !has_markdown_link(marks) && !has_markdown_link(enclosing);
            std::size_t group_end = code_node ? i + 1 : content.size();
            InlineRun run;
            std::string group;
            std::size_t text_begin = 0;
            std::size_t j = i;
            while (j < group_end) {
                const Node& child = document_.node(content[j]);
                if (enclosing.empty() ? !(child.marks == first.marks) : !(without_enclosing(child.marks) == marks)) {
                    break;
                }
                if (in_code && node_forms_ && declared_inline_spec(child) != nullptr) {
                    break;
                }
                bool ends_text = escape_links && child.type != "text";
                if (ends_text) {
                    escape_autolinks(group, text_begin);
                }
                group += render_inline_content(child, ctx, in_code, enclosing);
                if (ends_text) {
                    text_begin = group.size();
                }
                ++j;
            }
            if (escape_links) {
                escape_autolinks(group, text_begin);
            }

            for (const Mark& mark : marks) {
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
        const NodeSpec* spec = node_forms_ ? declared_inline_spec(node) : nullptr;
        bool in_code = has_mark(node.marks, "code");
        bool skip_code = in_code;
        if (spec != nullptr) {
            in_code = false;
        }
        std::string rendered = render_inline_content(node, ctx, in_code, {});
        if (!in_code && node.type == "text" && !has_markdown_link(node.marks)) {
            escape_autolinks(rendered);
        }
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
        return marktip::plain_text(document_, node);
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

std::string to_markdown(const Document& document, bool canonical) {
    MarkdownWriter writer(document);
    return writer.render(canonical);
}

std::optional<StoredSpelling> dump_spelling(const Document& document) {
    MarkdownWriter writer(document);
    return writer.dump_spelling();
}

}  // namespace marktip
