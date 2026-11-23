#pragma once

#include <string>
#include <string_view>

#include "schema.h"
#include "value.h"

namespace marktip {

struct Node;
class Document;

struct CodeInfo {
    std::string value;
    std::string word;
    const char* field;
};

std::string_view fence_info_word(std::string_view line);
CodeInfo code_info(const AttrList& attrs);
const AttrValue* carrier_body(const NodeSpec& spec, const AttrList& attrs);
const AttrValue* fence_body(const NodeSpec& spec, const AttrList& attrs, bool table_cell);
bool inline_math_body_allowed(std::string_view body, bool table_cell, bool marked);
bool inline_math_boundary(std::string_view surrounding, bool before);
bool has_tag_attr(const AttrList& attrs, const std::vector<AttrSpec>& specs);
bool uses_cell_textblock_tag(const NodeSpec& spec);
bool uses_tag_form(const Document& document, const Node& node, const NodeSpec& spec);
bool uses_tag_form(const Mark& mark, const MarkSpec& spec);

}  // namespace marktip
