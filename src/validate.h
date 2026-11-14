#pragma once

#include <string>
#include <variant>
#include <vector>

#include "path.h"
#include "schema.h"
#include "value.h"

namespace marktip {

struct OtherValue {};
struct OverflowInt {};

using AttrInput = std::variant<std::monostate, bool, long long, std::string,
                               std::vector<long long>, OtherValue, OverflowInt>;

bool attr_reads_string(const AttrSpec& spec);
void check_attr_value(const AttrInput& value, const AttrSpec& spec, const PathStack& path);
void check_mark_set(const std::vector<Mark>& existing, const Mark& mark, const Schema& schema,
                    const PathStack& path);

}  // namespace marktip
