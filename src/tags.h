#pragma once

#include <string>
#include <vector>

#include "schema.h"
#include "value.h"

namespace marktip {

std::string open_tag(const Schema& schema, const Mark& mark);
std::string close_tag(const Schema& schema, const Mark& mark);
void order_tag_marks(std::vector<Mark>& marks, const Schema& schema);

}  // namespace marktip
