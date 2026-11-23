#pragma once

#include <algorithm>

#include "md4c.h"

#include "ast.h"
#include "form.h"
#include "tags.h"

namespace marktip {

inline bool has_mark(const std::vector<Mark>& marks, std::string_view type) {
    return std::any_of(marks.begin(), marks.end(), [type](const Mark& mark) {
        return std::string_view(mark.type) == type;
    });
}

inline bool same_run_marks(const std::vector<Mark>& left, const std::vector<Mark>& right) {
    return left == right;
}

inline std::size_t common_prefix(const std::vector<Mark>& left, const std::vector<Mark>& right) {
    std::size_t count = 0;
    while (count < left.size() && count < right.size() && left[count] == right[count]) {
        ++count;
    }
    return count;
}

inline unsigned emphasis_bit(const Mark& mark) {
    std::string_view type = mark.type;
    if (type == "bold") return 1;
    if (type == "italic") return 2;
    if (type == "strike") return 4;
    return 0;
}

inline unsigned character_category(std::string_view text, bool trailing, bool cjk_friendly, MD_SIZE& width) {
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

inline unsigned inline_edge(const Node& node, bool trailing, bool cjk_friendly) {
    if (std::string_view(node.type) == "text") {
        MD_SIZE width;
        return character_category(node.text, trailing, cjk_friendly, width);
    }
    return node.type == "hardBreak" ? MD_ATTN_SPACE : MD_ATTN_PUNCT;
}

inline void remove_enclosing_marks(std::vector<Mark>& marks, const std::vector<Mark>& enclosing) {
    if (!enclosing.empty()) {
        marks.erase(std::remove_if(marks.begin(), marks.end(), [&](const Mark& mark) {
            return std::find(enclosing.begin(), enclosing.end(), mark) != enclosing.end();
        }), marks.end());
    }
}

inline std::vector<Mark> enclosing_delimiters(const Schema& schema, const std::vector<Mark>& enclosing,
                                             const std::vector<Mark>& marks) {
    auto inner = enclosing;
    for (const Mark& mark : marks) {
        if (mark.type != "code" && !uses_tag_form(mark, *schema.mark(mark.type)) &&
            std::find(inner.begin(), inner.end(), mark) == inner.end()) {
            inner.push_back(mark);
        }
    }
    return inner;
}

inline const NodeSpec* declared_inline_spec(const Schema& schema, const Node& node) {
    const std::string& type = node.type;
    if (type == "text" || type == "hardBreak" || type == "image" || type == "htmlInline") {
        return nullptr;
    }
    const NodeSpec& spec = *schema.node(type);
    return !spec.core && (spec.shape == Shape::InlineAtom || spec.shape == Shape::InlineContainer) ? &spec : nullptr;
}

struct InlineRun {
    std::size_t begin;
    std::size_t end;
    const std::vector<Mark>& marks;
    bool in_code;

    std::vector<Mark> delimiter_marks(const Schema& schema, bool extended) const {
        std::vector<Mark> result;
        for (const Mark& mark : marks) {
            if (mark.type != "code") {
                result.push_back(mark);
            }
        }
        if (extended) {
            // Tag marks enclose Markdown delimiters in the written run.
            order_tag_marks(result, schema);
        }
        return result;
    }
};

template <typename Visit>
void for_each_inline_run(const Document& document, const std::vector<std::size_t>& content,
                         const std::vector<Mark>& enclosing, bool node_forms, Visit visit) {
    std::vector<Mark> filtered;
    std::vector<Mark> next_filtered;
    auto marks_at = [&](std::size_t position, std::vector<Mark>& scratch) -> const std::vector<Mark>& {
        const auto& marks = document.node(content[position]).marks;
        if (enclosing.empty()) {
            return marks;
        }
        scratch = marks;
        remove_enclosing_marks(scratch, enclosing);
        return scratch;
    };
    auto separates_code = [&](std::size_t position) {
        return node_forms && declared_inline_spec(document.schema(), document.node(content[position])) != nullptr;
    };
    for (std::size_t begin = 0; begin < content.size();) {
        const auto& marks = marks_at(begin, filtered);
        bool in_code = has_mark(marks, "code");
        bool code_node = in_code && separates_code(begin);
        std::size_t end = begin + 1;
        if (!code_node) {
            while (end < content.size() && same_run_marks(marks, marks_at(end, next_filtered)) &&
                   (!in_code || !separates_code(end))) {
                ++end;
            }
        }
        visit(InlineRun {begin, end, marks, in_code && !code_node});
        begin = end;
    }
}

}  // namespace marktip
