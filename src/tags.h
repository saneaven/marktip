#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "schema.h"
#include "value.h"

namespace marktip {

// Views borrow the payload so undeclared constructs keep their original HTML spelling.
struct HtmlAttr {
    std::string_view name;
    std::optional<std::string_view> value;
};

struct HtmlConstruct {
    std::string_view raw;
    std::string_view name;
    bool closing = false;
    bool self_closing = false;
    std::vector<HtmlAttr> attrs = {};
};

std::vector<HtmlConstruct> tokenize_html(std::string_view html);
bool contains_declared_tag(std::string_view html, const Schema& schema);
bool starts_declared_tag(std::string_view html, const Schema& schema);

std::string open_tag(const Schema& schema, const Mark& mark);
std::string close_tag(const Schema& schema, const Mark& mark);
std::string open_node_tag(const NodeSpec& spec, const AttrList& attrs);
std::string close_node_tag(const NodeSpec& spec, const AttrList& attrs);
void order_tag_marks(std::vector<Mark>& marks, const Schema& schema);

}  // namespace marktip
