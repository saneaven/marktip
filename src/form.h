#pragma once

#include <string>
#include <string_view>

#include "schema.h"
#include "value.h"

namespace marktip {

struct Node;

struct CodeInfo {
    std::string value;
    std::string word;
    const char* field;
};

CodeInfo code_info(const AttrList& attrs);
const AttrValue* carrier_body(const NodeSpec& spec, const AttrList& attrs);
const AttrValue* fence_body(const NodeSpec& spec, const AttrList& attrs, bool table_cell);
bool inline_math_body_allowed(std::string_view body, bool table_cell, bool marked);
bool inline_math_boundary(std::string_view surrounding, bool before);
bool uses_tag_form(const Node& node, const NodeSpec& spec);
bool uses_tag_form(const Mark& mark, const MarkSpec& spec);

}  // namespace marktip
