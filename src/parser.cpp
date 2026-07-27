#include "parser.h"

#include "md4c.h"

extern "C" {
#include "entity.h"
}

#include <algorithm>
#include <cstddef>
#include <iterator>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "errors.h"

namespace py = pybind11;

namespace marktip {
namespace {

std::string md_attribute_to_string(const MD_ATTRIBUTE& attribute) {
    std::string out;
    out.reserve(attribute.size);
    if (attribute.size == 0 || attribute.text == nullptr) {
        return out;
    }
    if (attribute.substr_offsets == nullptr || attribute.substr_types == nullptr) {
        out.append(attribute.text, attribute.size);
        return out;
    }

    for (unsigned i = 0;; ++i) {
        MD_OFFSET begin = attribute.substr_offsets[i];
        MD_OFFSET end = attribute.substr_offsets[i + 1];
        MD_TEXTTYPE type = attribute.substr_types[i];
        if (type == MD_TEXT_NULLCHAR) {
            out.append("\xEF\xBF\xBD");
        } else {
            out.append(attribute.text + begin, end - begin);
        }
        if (static_cast<MD_SIZE>(end) >= attribute.size) {
            break;
        }
    }
    return out;
}

void append_utf8(std::string& out, unsigned codepoint) {
    if (codepoint == 0 || codepoint > 0x10FFFF || (codepoint >= 0xD800 && codepoint <= 0xDFFF)) {
        codepoint = 0xFFFD;
    }
    if (codepoint < 0x80) {
        out.push_back(static_cast<char>(codepoint));
    } else if (codepoint < 0x800) {
        out.push_back(static_cast<char>(0xC0 | (codepoint >> 6)));
        out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    } else if (codepoint < 0x10000) {
        out.push_back(static_cast<char>(0xE0 | (codepoint >> 12)));
        out.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    } else {
        out.push_back(static_cast<char>(0xF0 | (codepoint >> 18)));
        out.push_back(static_cast<char>(0x80 | ((codepoint >> 12) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    }
}

// Decode an entity reported by md4c ("&amp;", "&#65;", "&#x41;"; delimiters included).
std::string decode_entity(std::string_view value) {
    if (value.size() >= 4 && value[1] == '#') {
        bool hex = value[2] == 'x' || value[2] == 'X';
        std::size_t i = hex ? 3 : 2;
        unsigned codepoint = 0;
        bool any_digit = false;
        for (; i + 1 < value.size(); ++i) {
            char ch = value[i];
            unsigned digit;
            if (ch >= '0' && ch <= '9') {
                digit = static_cast<unsigned>(ch - '0');
            } else if (hex && ch >= 'a' && ch <= 'f') {
                digit = static_cast<unsigned>(ch - 'a' + 10);
            } else if (hex && ch >= 'A' && ch <= 'F') {
                digit = static_cast<unsigned>(ch - 'A' + 10);
            } else {
                return std::string(value);
            }
            codepoint = codepoint * (hex ? 16 : 10) + digit;
            if (codepoint > 0x10FFFF) {
                codepoint = 0x110000;
            }
            any_digit = true;
        }
        if (!any_digit) {
            return std::string(value);
        }
        std::string out;
        append_utf8(out, codepoint);
        return out;
    }

    const ENTITY* entity = entity_lookup(value.data(), value.size());
    if (entity == nullptr) {
        return std::string(value);
    }
    std::string out;
    append_utf8(out, entity->codepoints[0]);
    if (entity->codepoints[1] != 0) {
        append_utf8(out, entity->codepoints[1]);
    }
    return out;
}

bool is_br_tag(std::string_view value) {
    if (value.size() < 4 || value.front() != '<' || value.back() != '>') {
        return false;
    }
    auto lower = [](char ch) { return ch >= 'A' && ch <= 'Z' ? static_cast<char>(ch + 32) : ch; };
    if (lower(value[1]) != 'b' || lower(value[2]) != 'r') {
        return false;
    }
    std::size_t i = 3;
    while (i + 1 < value.size() && (value[i] == ' ' || value[i] == '\t')) {
        ++i;
    }
    if (value[i] == '/') {
        ++i;
    }
    return i == value.size() - 1;
}

std::string align_to_string(MD_ALIGN align) {
    switch (align) {
        case MD_ALIGN_LEFT:
            return "left";
        case MD_ALIGN_CENTER:
            return "center";
        case MD_ALIGN_RIGHT:
            return "right";
        case MD_ALIGN_DEFAULT:
        default:
            return "";
    }
}

class AstBuilder {
public:
    explicit AstBuilder(std::size_t input_size = 0, bool html = true)
        : document_(std::max<std::size_t>(32, input_size / 24)), html_(html) {
        stack_.push_back(0);
    }

    int enter_block(MD_BLOCKTYPE type, void* detail) {
        switch (type) {
            case MD_BLOCK_DOC:
                return 0;
            case MD_BLOCK_QUOTE:
                push_node("blockquote");
                return 0;
            case MD_BLOCK_UL: {
                auto* ul = static_cast<MD_BLOCK_UL_DETAIL*>(detail);
                AttrList attrs;
                if (ul != nullptr) {
                    set_attr(attrs, "tight", AttrValue::boolean(ul->is_tight != 0));
                }
                push_node("bulletList", std::move(attrs));
                return 0;
            }
            case MD_BLOCK_OL: {
                auto* ol = static_cast<MD_BLOCK_OL_DETAIL*>(detail);
                AttrList attrs;
                set_attr(attrs, "start", AttrValue::integer(ol != nullptr ? ol->start : 1));
                if (ol != nullptr) {
                    set_attr(attrs, "tight", AttrValue::boolean(ol->is_tight != 0));
                }
                push_node("orderedList", std::move(attrs));
                return 0;
            }
            case MD_BLOCK_LI: {
                auto* li = static_cast<MD_BLOCK_LI_DETAIL*>(detail);
                AttrList attrs;
                if (li != nullptr && li->is_task) {
                    set_attr(attrs, "checked", AttrValue::boolean(li->task_mark == 'x' || li->task_mark == 'X'));
                    push_node("taskItem", std::move(attrs));
                } else {
                    push_node("listItem");
                }
                return 0;
            }
            case MD_BLOCK_HR:
                push_node("horizontalRule");
                return 0;
            case MD_BLOCK_H: {
                auto* heading = static_cast<MD_BLOCK_H_DETAIL*>(detail);
                AttrList attrs;
                set_attr(attrs, "level", AttrValue::integer(heading != nullptr ? heading->level : 1));
                push_node("heading", std::move(attrs));
                return 0;
            }
            case MD_BLOCK_CODE: {
                auto* code = static_cast<MD_BLOCK_CODE_DETAIL*>(detail);
                AttrList attrs;
                if (code != nullptr) {
                    std::string language = md_attribute_to_string(code->lang);
                    std::string info = md_attribute_to_string(code->info);
                    if (!language.empty()) {
                        set_attr(attrs, "language", AttrValue::string(std::move(language)));
                    }
                    if (!info.empty()) {
                        set_attr(attrs, "info", AttrValue::string(std::move(info)));
                    }
                }
                push_node("codeBlock", std::move(attrs));
                return 0;
            }
            case MD_BLOCK_HTML:
                push_node("htmlBlock");
                return 0;
            case MD_BLOCK_P:
                push_node("paragraph");
                return 0;
            case MD_BLOCK_TABLE: {
                auto* table = static_cast<MD_BLOCK_TABLE_DETAIL*>(detail);
                AttrList attrs;
                if (table != nullptr) {
                    set_attr(attrs, "colCount", AttrValue::integer(table->col_count));
                }
                push_node("table", std::move(attrs));
                return 0;
            }
            case MD_BLOCK_THEAD:
            case MD_BLOCK_TBODY:
                return 0;
            case MD_BLOCK_TR:
                push_node("tableRow");
                return 0;
            case MD_BLOCK_TH:
            case MD_BLOCK_TD: {
                auto* cell = static_cast<MD_BLOCK_TD_DETAIL*>(detail);
                AttrList attrs;
                if (cell != nullptr) {
                    std::string align = align_to_string(cell->align);
                    if (!align.empty()) {
                        set_attr(attrs, "align", AttrValue::string(std::move(align)));
                    }
                }
                push_node(type == MD_BLOCK_TH ? "tableHeader" : "tableCell", std::move(attrs));
                return 0;
            }
        }
        return 0;
    }

    int leave_block(MD_BLOCKTYPE type, void*) {
        switch (type) {
            case MD_BLOCK_DOC:
            case MD_BLOCK_THEAD:
            case MD_BLOCK_TBODY:
                return 0;
            case MD_BLOCK_UL:
                normalize_task_list(stack_.back());
                pop_node();
                return 0;
            case MD_BLOCK_LI:
            case MD_BLOCK_TH:
            case MD_BLOCK_TD:
                wrap_inline_runs_in_paragraph(stack_.back());
                pop_node();
                return 0;
            default:
                pop_node();
                return 0;
        }
    }

    int enter_span(MD_SPANTYPE type, void* detail) {
        switch (type) {
            case MD_SPAN_EM:
                active_marks_.push_back(Mark{"italic", {}});
                return 0;
            case MD_SPAN_STRONG:
                active_marks_.push_back(Mark{"bold", {}});
                return 0;
            case MD_SPAN_A: {
                auto* link = static_cast<MD_SPAN_A_DETAIL*>(detail);
                AttrList attrs;
                if (link != nullptr) {
                    set_attr(attrs, "href", AttrValue::string(md_attribute_to_string(link->href)));
                    std::string title = md_attribute_to_string(link->title);
                    if (!title.empty()) {
                        set_attr(attrs, "title", AttrValue::string(std::move(title)));
                    }
                }
                active_marks_.push_back(Mark{"link", std::move(attrs)});
                return 0;
            }
            case MD_SPAN_IMG: {
                auto* image = static_cast<MD_SPAN_IMG_DETAIL*>(detail);
                AttrList attrs;
                if (image != nullptr) {
                    set_attr(attrs, "src", AttrValue::string(md_attribute_to_string(image->src)));
                    std::string title = md_attribute_to_string(image->title);
                    if (!title.empty()) {
                        set_attr(attrs, "title", AttrValue::string(std::move(title)));
                    }
                }
                set_attr(attrs, "alt", AttrValue::string(""));
                std::size_t index = append_node("image", std::move(attrs));
                document_.node(index).marks = active_marks_;
                push_index(index);
                return 0;
            }
            case MD_SPAN_CODE:
                active_marks_.push_back(Mark{"code", {}});
                return 0;
            case MD_SPAN_DEL:
                active_marks_.push_back(Mark{"strike", {}});
                return 0;
            case MD_SPAN_LATEXMATH:
            case MD_SPAN_LATEXMATH_DISPLAY:
            case MD_SPAN_WIKILINK:
            case MD_SPAN_U:
                return 0;
        }
        return 0;
    }

    int leave_span(MD_SPANTYPE type, void*) {
        switch (type) {
            case MD_SPAN_EM:
                pop_mark("italic");
                return 0;
            case MD_SPAN_STRONG:
                pop_mark("bold");
                return 0;
            case MD_SPAN_A:
                pop_mark("link");
                return 0;
            case MD_SPAN_IMG:
                finalize_image(stack_.back());
                pop_node();
                return 0;
            case MD_SPAN_CODE:
                pop_mark("code");
                return 0;
            case MD_SPAN_DEL:
                pop_mark("strike");
                return 0;
            case MD_SPAN_LATEXMATH:
            case MD_SPAN_LATEXMATH_DISPLAY:
            case MD_SPAN_WIKILINK:
            case MD_SPAN_U:
                return 0;
        }
        return 0;
    }

    int text(MD_TEXTTYPE type, const MD_CHAR* text, MD_SIZE size) {
        switch (type) {
            case MD_TEXT_NULLCHAR:
                add_text("\xEF\xBF\xBD");
                return 0;
            case MD_TEXT_BR:
                add_hard_break();
                return 0;
            case MD_TEXT_SOFTBR:
                add_text("\n");
                return 0;
            case MD_TEXT_HTML:
                if (current().type == "htmlBlock") {
                    append_html_block(std::string_view(text, size));
                } else {
                    add_html_inline(std::string_view(text, size));
                }
                return 0;
            case MD_TEXT_CODE:
                if (current().type == "codeBlock") {
                    append_code_text(std::string_view(text, size));
                } else {
                    add_text(std::string_view(text, size));
                }
                return 0;
            case MD_TEXT_ENTITY:
                add_text(decode_entity(std::string_view(text, size)));
                return 0;
            case MD_TEXT_NORMAL:
            case MD_TEXT_LATEXMATH:
                add_text(std::string_view(text, size));
                return 0;
        }
        return 0;
    }

    // First error wins: MD4C keeps calling back until it unwinds,
    // and the original failure is the informative one.
    void set_error(std::string code, std::string message) {
        if (error_.empty()) {
            error_code_ = std::move(code);
            error_ = std::move(message);
        }
    }

    const std::string& error() const {
        return error_;
    }

    const std::string& error_code() const {
        return error_code_;
    }

    Document into_document() && {
        return std::move(document_);
    }

private:
    Document document_;
    std::vector<std::size_t> stack_;
    std::vector<Mark> active_marks_;
    std::string error_;
    std::string error_code_;
    bool html_ = true;

    Node& current() {
        return document_.node(stack_.back());
    }

    const Node& current() const {
        return document_.node(stack_.back());
    }

    std::size_t append_node(std::string type, AttrList attrs = {}) {
        Node node;
        node.type = std::move(type);
        node.attrs = std::move(attrs);
        return document_.append_child(stack_.back(), std::move(node));
    }

    void push_index(std::size_t index) {
        if (stack_.size() >= kMaxNodeDepth) {
            throw ParseError("markdown_max_depth", "markdown nesting exceeds maximum depth");
        }
        stack_.push_back(index);
    }

    void push_node(std::string type, AttrList attrs = {}) {
        push_index(append_node(std::move(type), std::move(attrs)));
    }

    void pop_node() {
        if (stack_.size() > 1) {
            stack_.pop_back();
        }
    }

    void pop_mark(std::string_view type) {
        for (auto it = active_marks_.rbegin(); it != active_marks_.rend(); ++it) {
            if (it->type == type) {
                active_marks_.erase(std::next(it).base());
                return;
            }
        }
    }

    void add_text(std::string_view value) {
        if (value.empty()) {
            return;
        }

        std::size_t parent_index = stack_.back();
        Node& parent = document_.node(parent_index);
        if (!parent.content.empty()) {
            Node& last = document_.node(parent.content.back());
            if (last.type == "text" && last.marks == active_marks_) {
                last.text.append(value.data(), value.size());
                return;
            }
        }

        Node node;
        node.type = "text";
        node.text.assign(value.data(), value.size());
        node.marks = active_marks_;
        document_.append_child(parent_index, std::move(node));
    }

    void append_code_text(std::string_view value) {
        if (value.empty()) {
            return;
        }

        std::size_t parent_index = stack_.back();
        Node& parent = document_.node(parent_index);
        if (!parent.content.empty()) {
            Node& last = document_.node(parent.content.back());
            if (last.type == "text" && last.marks.empty()) {
                last.text.append(value.data(), value.size());
                return;
            }
        }

        Node node;
        node.type = "text";
        node.text.assign(value.data(), value.size());
        document_.append_child(parent_index, std::move(node));
    }

    void add_hard_break() {
        Node node;
        node.type = "hardBreak";
        node.marks = active_marks_;
        document_.append_child(stack_.back(), std::move(node));
    }

    void append_html_block(std::string_view value) {
        Node& node = current();
        std::string html = attr_string(node.attrs, "html");
        html.append(value.data(), value.size());
        set_attr(node.attrs, "html", AttrValue::string(std::move(html)));
    }

    void add_html_inline(std::string_view value) {
        if (value.empty()) {
            return;
        }

        // Table cells cannot hold literal newlines, so hard breaks in cells are
        // serialized as <br>; map them back to hardBreak when parsing. This
        // must stay ahead of the html_ gate so marktip's own cell output
        // round-trips even with html disabled.
        if (is_br_tag(value) && (current().type == "tableCell" || current().type == "tableHeader")) {
            add_hard_break();
            return;
        }

        if (!html_) {
            add_text(value);
            return;
        }

        std::size_t parent_index = stack_.back();
        Node& parent = document_.node(parent_index);
        if (!parent.content.empty()) {
            Node& last = document_.node(parent.content.back());
            if (last.type == "htmlInline" && last.marks == active_marks_) {
                std::string html = attr_string(last.attrs, "html");
                html.append(value.data(), value.size());
                set_attr(last.attrs, "html", AttrValue::string(std::move(html)));
                return;
            }
        }

        AttrList attrs;
        set_attr(attrs, "html", AttrValue::string(std::string(value)));
        Node node;
        node.type = "htmlInline";
        node.attrs = std::move(attrs);
        node.marks = active_marks_;
        document_.append_child(parent_index, std::move(node));
    }

    std::string flatten_plain_text(std::size_t index) const {
        const Node& node = document_.node(index);
        if (node.type == "text") {
            return node.text;
        }
        if (node.type == "hardBreak") {
            return "\n";
        }
        if (node.type == "htmlInline") {
            return attr_string(node.attrs, "html");
        }
        if (node.type == "image") {
            return attr_string(node.attrs, "alt");
        }

        std::string out;
        for (std::size_t child : node.content) {
            out += flatten_plain_text(child);
        }
        return out;
    }

    void finalize_image(std::size_t index) {
        Node& node = document_.node(index);
        std::string alt;
        for (std::size_t child : node.content) {
            alt += flatten_plain_text(child);
        }
        set_attr(node.attrs, "alt", AttrValue::string(std::move(alt)));
        node.content.clear();
    }

    void normalize_task_list(std::size_t index) {
        Node& list = document_.node(index);
        if (list.type != "bulletList") {
            return;
        }

        bool has_task = false;
        for (std::size_t child : list.content) {
            if (document_.node(child).type == "taskItem") {
                has_task = true;
                break;
            }
        }
        if (!has_task) {
            return;
        }

        list.type = "taskList";
        for (std::size_t child : list.content) {
            Node& item = document_.node(child);
            if (item.type == "listItem") {
                item.type = "taskItem";
                set_attr(item.attrs, "checked", AttrValue::boolean(false));
            }
        }
    }

    bool is_inline_node(std::size_t index) const {
        const std::string& type = document_.node(index).type;
        return type == "text" || type == "hardBreak" || type == "image" || type == "htmlInline";
    }

    void wrap_inline_runs_in_paragraph(std::size_t index) {
        std::vector<std::size_t> original = document_.node(index).content;
        std::vector<std::size_t> rebuilt;
        std::vector<std::size_t> inline_run;

        auto flush = [&]() {
            if (inline_run.empty()) {
                return;
            }

            Node paragraph;
            paragraph.type = "paragraph";
            paragraph.content = std::move(inline_run);
            rebuilt.push_back(document_.append_node(std::move(paragraph)));
            inline_run = {};
        };

        for (std::size_t child : original) {
            if (is_inline_node(child)) {
                inline_run.push_back(child);
            } else {
                flush();
                rebuilt.push_back(child);
            }
        }
        flush();

        document_.node(index).content = std::move(rebuilt);
    }
};

// MD4C callbacks are a C boundary, so an exception must not escape one.
// Stash its code and message on the builder and return nonzero instead;
// parse_to_document rethrows once md_parse has unwound.
template <typename Fn>
int run_callback(void* userdata, Fn&& fn) noexcept {
    auto* builder = static_cast<AstBuilder*>(userdata);
    try {
        return fn(*builder);
    } catch (const MarktipError& exc) {
        builder->set_error(exc.code(), exc.what());
    } catch (const std::exception& exc) {
        builder->set_error("parse_failed", exc.what());
    } catch (...) {
        builder->set_error("parse_failed", "unknown parser callback failure");
    }
    return 1;
}

int enter_block_callback(MD_BLOCKTYPE type, void* detail, void* userdata) noexcept {
    return run_callback(userdata, [&](AstBuilder& builder) { return builder.enter_block(type, detail); });
}

int leave_block_callback(MD_BLOCKTYPE type, void* detail, void* userdata) noexcept {
    return run_callback(userdata, [&](AstBuilder& builder) { return builder.leave_block(type, detail); });
}

int enter_span_callback(MD_SPANTYPE type, void* detail, void* userdata) noexcept {
    return run_callback(userdata, [&](AstBuilder& builder) { return builder.enter_span(type, detail); });
}

int leave_span_callback(MD_SPANTYPE type, void* detail, void* userdata) noexcept {
    return run_callback(userdata, [&](AstBuilder& builder) { return builder.leave_span(type, detail); });
}

int text_callback(MD_TEXTTYPE type, const MD_CHAR* text, MD_SIZE size, void* userdata) noexcept {
    return run_callback(userdata, [&](AstBuilder& builder) { return builder.text(type, text, size); });
}

Document parse_to_document(const std::string& markdown, bool cjk_friendly, bool html) {
    AstBuilder builder(markdown.size(), html);
    MD_PARSER parser {};
    parser.abi_version = 0;
    // With html=false, block-level raw HTML degrades to paragraph text via
    // MD_FLAG_NOHTMLBLOCKS. Inline HTML spans stay recognized (no
    // MD_FLAG_NOHTMLSPANS) so the <br>-in-cell hardBreak mapping keeps
    // working; AstBuilder turns the remaining spans into literal text.
    parser.flags = MD_DIALECT_GITHUB | (cjk_friendly ? MD_FLAG_CJKFRIENDLYEMPHASIS : 0) |
                   (html ? 0 : MD_FLAG_NOHTMLBLOCKS);
    parser.enter_block = enter_block_callback;
    parser.leave_block = leave_block_callback;
    parser.enter_span = enter_span_callback;
    parser.leave_span = leave_span_callback;
    parser.text = text_callback;
    parser.debug_log = nullptr;
    parser.syntax = nullptr;

    int rc = md_parse(markdown.data(), static_cast<MD_SIZE>(markdown.size()), &parser, &builder);
    if (rc != 0) {
        if (!builder.error().empty()) {
            throw ParseError(builder.error_code(), builder.error());
        }
        throw ParseError("parse_failed", "MD4C failed to parse markdown");
    }
    return std::move(builder).into_document();
}

}  // namespace

Document from_markdown_py(py::object markdown, bool cjk_friendly, bool html) {
    std::string input;
    if (py::isinstance<py::str>(markdown) || py::isinstance<py::bytes>(markdown)) {
        input = py::cast<std::string>(markdown);
    } else {
        throw py::type_error("from_markdown() expects str or bytes");
    }

    Document document;
    {
        py::gil_scoped_release release;
        document = parse_to_document(input, cjk_friendly, html);
    }
    return document;
}

}  // namespace marktip
