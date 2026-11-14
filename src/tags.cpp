#include "tags.h"

#include <algorithm>
#include <string_view>
#include <utility>


namespace marktip {
namespace {

bool ascii_letter(char ch) {
    return (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z');
}

bool ascii_digit(char ch) {
    return ch >= '0' && ch <= '9';
}

bool tag_name_char(char ch) {
    return ascii_letter(ch) || ascii_digit(ch) || ch == '-';
}

bool attr_name_start(char ch) {
    return ascii_letter(ch) || ch == '_' || ch == ':';
}

bool attr_name_char(char ch) {
    return attr_name_start(ch) || ascii_digit(ch) || ch == '.' || ch == '-';
}

bool html_space(char ch) {
    return ch == ' ' || ch == '\t' || ch == '\v' || ch == '\f' || ch == '\r' || ch == '\n';
}

bool unquoted_end(char ch) {
    return ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n' ||
           ch == '"' || ch == '\'' || ch == '=' || ch == '<' || ch == '>' || ch == '`';
}

bool parse_html_tag(std::string_view html, std::size_t begin, HtmlConstruct& tag) {
    std::size_t off = begin + 1;
    if (off < html.size() && html[off] == '/') {
        tag.closing = true;
        ++off;
    }
    if (off >= html.size() || !ascii_letter(html[off])) {
        return false;
    }
    std::size_t name_begin = off++;
    while (off < html.size() && tag_name_char(html[off])) {
        ++off;
    }
    tag.name = html.substr(name_begin, off - name_begin);

    int state = tag.closing ? -1 : 0;
    std::size_t value_begin = 0;
    while (off < html.size()) {
        char ch = html[off];
        if (state > 40) {
            if ((state == 41 && unquoted_end(ch)) ||
                (state == 42 && ch == '\'') || (state == 43 && ch == '"')) {
                tag.attrs.back().value = html.substr(value_begin, off - value_begin);
                bool unquoted = state == 41;
                state = 0;
                if (!unquoted) {
                    ++off;
                }
            } else {
                ++off;
            }
        } else if (html_space(ch)) {
            if (state == 0) {
                state = 1;
            }
            ++off;
        } else if (state <= 2 && ch == '>') {
            tag.raw = html.substr(begin, off + 1 - begin);
            return true;
        } else if (state <= 2 && ch == '/' && off + 1 < html.size() && html[off + 1] == '>') {
            tag.self_closing = true;
            tag.raw = html.substr(begin, off + 2 - begin);
            return true;
        } else if ((state == 1 || state == 2) && attr_name_start(ch)) {
            std::size_t attr_begin = off++;
            while (off < html.size() && attr_name_char(html[off])) {
                ++off;
            }
            tag.attrs.push_back({html.substr(attr_begin, off - attr_begin), std::nullopt});
            state = 2;
        } else if (state == 2 && ch == '=') {
            ++off;
            state = 3;
        } else if (state == 3) {
            if (ch == '"' || ch == '\'') {
                state = ch == '\'' ? 42 : 43;
                value_begin = ++off;
            } else if (!unquoted_end(ch)) {
                state = 41;
                value_begin = off++;
            } else {
                return false;
            }
        } else {
            return false;
        }
    }
    return false;
}

std::size_t opaque_html_end(std::string_view html, std::size_t begin) {
    std::string_view tail = html.substr(begin);
    std::string_view closer;
    std::size_t search = begin + 2;
    std::size_t line_end = html.find_first_of("\r\n", begin);
    if (line_end == std::string_view::npos) {
        line_end = html.size();
    }
    while (html[line_end - 1] == ' ' || html[line_end - 1] == '\t') {
        --line_end;
    }
    if (tail.substr(0, 4) == "<!--") {
        if (begin + 4 >= line_end) {
            return std::string_view::npos;
        }
        closer = "-->";
    } else if (tail.substr(0, 2) == "<?") {
        if (begin + 2 >= line_end) {
            return std::string_view::npos;
        }
        closer = "?>";
    } else if (tail.substr(0, 9) == "<![CDATA[") {
        if (begin + 9 >= line_end) {
            return std::string_view::npos;
        }
        closer = "]]>";
        search = begin + 9;
    } else if (tail.size() > 2 && tail[1] == '!' && ascii_letter(tail[2])) {
        closer = ">";
        search = begin + 3;
        while (search < html.size() && ascii_letter(html[search])) {
            ++search;
        }
    } else {
        return std::string_view::npos;
    }
    std::size_t end = html.find(closer, search);
    return end == std::string_view::npos ? end : end + closer.size();
}

void append_escaped_attr(std::string& out, std::string_view value) {
    for (unsigned char ch : value) {
        switch (ch) {
            case '&': out += "&amp;"; break;
            case '"': out += "&quot;"; break;
            case '<': out += "&lt;"; break;
            case '>': out += "&gt;"; break;
            case '|': out += "&#124;"; break;
            case '`': out += "&#96;"; break;
            default:
                if (ch < 0x20) {
                    out += "&#" + std::to_string(ch) + ";";
                } else {
                    out.push_back(static_cast<char>(ch));
                }
                break;
        }
    }
}

std::string open_tag(const std::vector<AttrSpec>& specs, const std::string& tag, const AttrList& attrs,
                     bool self_closing) {
    std::string out = "<" + tag;
    for (const AttrSpec& attr : specs) {
        const AttrValue* value = find_attr(attrs, attr.name);
        if (value == nullptr) {
            continue;
        }
        out += " " + attr.name + "=\"";
        switch (value->kind) {
            case AttrValue::Kind::String:
                append_escaped_attr(out, value->string_value);
                break;
            case AttrValue::Kind::Int:
                out += std::to_string(value->int_value);
                break;
            case AttrValue::Kind::Bool:
                out += value->bool_value ? "true" : "false";
                break;
        }
        out.push_back('"');
    }
    if (self_closing) {
        out.push_back('/');
    }
    out.push_back('>');
    return out;
}

}  // namespace

std::vector<HtmlConstruct> tokenize_html(std::string_view html) {
    std::vector<HtmlConstruct> constructs;
    std::size_t literal_begin = 0;
    std::size_t off = 0;
    while (off < html.size()) {
        off = html.find('<', off);
        if (off == std::string_view::npos) {
            break;
        }
        HtmlConstruct tag;
        if (parse_html_tag(html, off, tag)) {
            if (literal_begin != off) {
                constructs.push_back({html.substr(literal_begin, off - literal_begin), {}});
            }
            constructs.push_back(std::move(tag));
            off += constructs.back().raw.size();
            literal_begin = off;
            continue;
        }
        std::size_t end = opaque_html_end(html, off);
        if (end != std::string_view::npos) {
            if (literal_begin != off) {
                constructs.push_back({html.substr(literal_begin, off - literal_begin), {}});
            }
            constructs.push_back({html.substr(off, end - off), {}});
            off = end;
            literal_begin = off;
        } else {
            ++off;
        }
    }
    if (literal_begin != html.size()) {
        constructs.push_back({html.substr(literal_begin), {}});
    }
    return constructs;
}

bool contains_declared_tag(std::string_view html, const Schema& schema) {
    for (const HtmlConstruct& construct : tokenize_html(html)) {
        if (!construct.name.empty() && schema.tag(construct.name) != nullptr) {
            return true;
        }
    }
    return false;
}

bool starts_declared_tag(std::string_view html, const Schema& schema) {
    std::size_t off = 0;
    while (off < html.size() && html[off] == ' ' && off < 4) {
        ++off;
    }
    if (off >= 4 || off >= html.size() || html[off] != '<') {
        return false;
    }
    ++off;
    if (off < html.size() && html[off] == '/') {
        ++off;
    }
    if (off >= html.size() || !ascii_letter(html[off])) {
        return false;
    }
    std::size_t begin = off++;
    while (off < html.size() && tag_name_char(html[off])) {
        ++off;
    }
    if (off < html.size() && !html_space(html[off]) && html[off] != '/' && html[off] != '>') {
        return false;
    }
    return schema.tag(html.substr(begin, off - begin)) != nullptr;
}

std::string open_tag(const Schema& schema, const Mark& mark) {
    const MarkSpec& spec = *schema.mark(mark.type);
    return open_tag(spec.attrs, spec.tag, mark.attrs, false);
}

std::string close_tag(const Schema& schema, const Mark& mark) {
    return "</" + schema.mark(mark.type)->tag + ">";
}

std::string open_node_tag(const NodeSpec& spec, const AttrList& attrs) {
    return open_tag(spec.attrs, spec.tag, attrs,
                    spec.shape == Shape::InlineAtom || spec.shape == Shape::BlockAtom);
}

std::string close_node_tag(const NodeSpec& spec) {
    return "</" + spec.tag + ">";
}

void order_tag_marks(std::vector<Mark>& marks, const Schema& schema) {
    std::stable_partition(marks.begin(), marks.end(), [&](const Mark& mark) {
        return !schema.mark(mark.type)->core;
    });
}

}  // namespace marktip
