#pragma once

#include <string>
#include <string_view>

#include "schema.h"
#include "value.h"

namespace marktip {

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

}  // namespace marktip
