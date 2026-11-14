#include "tags.h"

#include <algorithm>
#include <string_view>

namespace marktip {
namespace {

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

}  // namespace

std::string open_tag(const Schema& schema, const Mark& mark) {
    const MarkSpec& spec = *schema.mark(mark.type);
    std::string out = "<" + spec.tag;
    for (const AttrSpec& attr : spec.attrs) {
        const AttrValue* value = find_attr(mark.attrs, attr.name);
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
    out.push_back('>');
    return out;
}

std::string close_tag(const Schema& schema, const Mark& mark) {
    return "</" + schema.mark(mark.type)->tag + ">";
}

void order_tag_marks(std::vector<Mark>& marks, const Schema& schema) {
    std::stable_partition(marks.begin(), marks.end(), [&](const Mark& mark) {
        return !schema.mark(mark.type)->core;
    });
}

}  // namespace marktip
