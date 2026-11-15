#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace marktip {

// CommonMark ordered-list markers are at most 9 digits and cannot be negative.
// The serializer clamps to this range; strict mode refuses instead.
inline constexpr long long kMaxListStart = 999999999;

struct AttrValue {
    enum class Kind { String, Int, Bool, IntList };

    Kind kind = Kind::String;
    std::string string_value;
    long long int_value = 0;
    bool bool_value = false;

    static AttrValue string(std::string value);
    static AttrValue integer(long long value);
    static AttrValue boolean(bool value);
    static AttrValue int_list(std::vector<long long> value);

    std::vector<long long> int_list_value() const;

    bool operator==(const AttrValue& other) const;
};

using AttrList = std::vector<std::pair<std::string, AttrValue>>;

struct Mark {
    std::string type;
    AttrList attrs;

    bool operator==(const Mark& other) const;
};

std::string normalize_content_string(std::string value);
std::optional<std::vector<long long>> parse_int_list(std::string_view value);

void set_attr(AttrList& attrs, std::string key, AttrValue value);
const AttrValue* find_attr(const AttrList& attrs, std::string_view key);
std::string attr_string(const AttrList& attrs, std::string_view key, std::string fallback = {});
long long attr_int(const AttrList& attrs, std::string_view key, long long fallback = 0);
bool attr_bool(const AttrList& attrs, std::string_view key, bool fallback = false);

}  // namespace marktip
