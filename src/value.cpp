#include "value.h"

#include <algorithm>
#include <charconv>

#include "tags.h"

namespace marktip {

// CommonMark replaces an insecure NUL with U+FFFD before parsing. from_dict
// has to make the same normalization or a dict write can serialize bytes that
// change the next time its Markdown is parsed. URI fields are deliberately
// excluded by their caller: raw controls there are an unconditional rejection.
std::string normalize_content_string(std::string value) {
    std::size_t nul = value.find('\0');
    if (nul == std::string::npos) {
        return value;
    }

    std::string normalized;
    normalized.reserve(value.size() + 2);
    std::size_t start = 0;
    while (nul != std::string::npos) {
        normalized.append(value, start, nul - start);
        normalized.append("\xEF\xBF\xBD");
        start = nul + 1;
        nul = value.find('\0', start);
    }
    normalized.append(value, start, std::string::npos);
    return normalized;
}

AttrValue AttrValue::string(std::string value) {
    AttrValue attr;
    attr.kind = Kind::String;
    attr.string_value = std::move(value);
    return attr;
}

AttrValue AttrValue::integer(long long value) {
    AttrValue attr;
    attr.kind = Kind::Int;
    attr.int_value = value;
    return attr;
}

AttrValue AttrValue::boolean(bool value) {
    AttrValue attr;
    attr.kind = Kind::Bool;
    attr.bool_value = value;
    return attr;
}

AttrValue AttrValue::int_list(std::vector<long long> value) {
    AttrValue attr;
    attr.kind = Kind::IntList;
    // Canonical spelling keeps list storage from enlarging every scalar attr.
    for (long long number : value) {
        if (!attr.string_value.empty()) {
            attr.string_value.push_back(',');
        }
        attr.string_value += std::to_string(number);
    }
    return attr;
}

AttrValue AttrValue::str_map(StrMapEntries value) {
    AttrValue attr;
    attr.kind = Kind::StrMap;
    // NUL separates keys and normalized values without enlarging scalar attrs.
    for (auto& entry : value) {
        attr.string_value += entry.first;
        attr.string_value.push_back('\0');
        attr.string_value += normalize_content_string(std::move(entry.second));
        attr.string_value.push_back('\0');
    }
    return attr;
}

StrMapEntries AttrValue::str_map_value() const {
    StrMapEntries entries;
    std::size_t begin = 0;
    while (begin < string_value.size()) {
        std::size_t key_end = string_value.find('\0', begin);
        std::size_t value_end = string_value.find('\0', key_end + 1);
        entries.emplace_back(string_value.substr(begin, key_end - begin),
                             string_value.substr(key_end + 1, value_end - key_end - 1));
        begin = value_end + 1;
    }
    return entries;
}

bool str_map_key(std::string_view key) {
    if (key.empty()) {
        return false;
    }
    for (char ch : key) {
        if (!attr_name_char(ch)) {
            return false;
        }
    }
    return true;
}

std::optional<long long> parse_decimal_int(std::string_view value) {
    if (!value.empty() && value.front() == '+') {
        value.remove_prefix(1);
        if (value.empty() || value.front() < '0' || value.front() > '9') {
            return std::nullopt;
        }
    }
    long long number;
    auto result = std::from_chars(value.data(), value.data() + value.size(), number);
    if (result.ec != std::errc {} || result.ptr != value.data() + value.size()) {
        return std::nullopt;
    }
    return number;
}

std::optional<std::vector<long long>> parse_int_list(std::string_view value) {
    std::vector<long long> numbers;
    if (value.empty()) {
        return numbers;
    }
    std::size_t begin = 0;
    while (true) {
        std::size_t end = value.find(',', begin);
        std::optional<long long> number = parse_decimal_int(value.substr(begin, end - begin));
        if (!number) {
            return std::nullopt;
        }
        numbers.push_back(*number);
        if (end == std::string_view::npos) {
            return numbers;
        }
        begin = end + 1;
    }
}

std::vector<long long> AttrValue::int_list_value() const {
    return std::move(*parse_int_list(string_value));
}

bool AttrValue::operator==(const AttrValue& other) const {
    if (kind != other.kind) {
        return false;
    }
    switch (kind) {
        case Kind::String:
        case Kind::IntList:
        case Kind::StrMap:
            return string_value == other.string_value;
        case Kind::Int:
            return int_value == other.int_value;
        case Kind::Bool:
            return bool_value == other.bool_value;
    }
    return false;
}

bool equal_attrs(const AttrList& left, const AttrList& right) {
    return left.size() == right.size() && std::all_of(left.begin(), left.end(), [&](const auto& attr) {
        return std::any_of(right.begin(), right.end(), [&](const auto& other) {
            return attr.first == other.first && attr.second == other.second;
        });
    });
}

bool Mark::operator==(const Mark& other) const {
    return type == other.type && equal_attrs(attrs, other.attrs);
}

void set_attr(AttrList& attrs, std::string key, AttrValue value) {
    for (auto& attr : attrs) {
        if (attr.first == key) {
            attr.second = std::move(value);
            return;
        }
    }
    attrs.emplace_back(std::move(key), std::move(value));
}

const AttrValue* find_attr(const AttrList& attrs, std::string_view key) {
    for (const auto& attr : attrs) {
        if (attr.first == key) {
            return &attr.second;
        }
    }
    return nullptr;
}

std::string attr_string(const AttrList& attrs, std::string_view key, std::string fallback) {
    const AttrValue* attr = find_attr(attrs, key);
    if (attr == nullptr) {
        return fallback;
    }
    if (attr->kind == AttrValue::Kind::String || attr->kind == AttrValue::Kind::IntList) {
        return attr->string_value;
    }
    if (attr->kind == AttrValue::Kind::Int) {
        return std::to_string(attr->int_value);
    }
    return attr->bool_value ? "true" : "false";
}

long long attr_int(const AttrList& attrs, std::string_view key, long long fallback) {
    const AttrValue* attr = find_attr(attrs, key);
    if (attr == nullptr) {
        return fallback;
    }
    if (attr->kind == AttrValue::Kind::Int) {
        return attr->int_value;
    }
    if (attr->kind == AttrValue::Kind::Bool) {
        return attr->bool_value ? 1 : 0;
    }
    try {
        return std::stoll(attr->string_value);
    } catch (...) {
        return fallback;
    }
}

bool attr_bool(const AttrList& attrs, std::string_view key, bool fallback) {
    const AttrValue* attr = find_attr(attrs, key);
    if (attr == nullptr) {
        return fallback;
    }
    if (attr->kind == AttrValue::Kind::Bool) {
        return attr->bool_value;
    }
    if (attr->kind == AttrValue::Kind::Int) {
        return attr->int_value != 0;
    }
    if (attr->string_value == "true" || attr->string_value == "1") {
        return true;
    }
    if (attr->string_value == "false" || attr->string_value == "0") {
        return false;
    }
    return fallback;
}

}  // namespace marktip
