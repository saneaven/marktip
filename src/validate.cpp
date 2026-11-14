#include "validate.h"

#include <algorithm>
#include <utility>

#include "errors.h"

namespace marktip {
namespace {

bool equal_attrs(const AttrList& left, const AttrList& right) {
    return left.size() == right.size() && std::all_of(left.begin(), left.end(), [&](const auto& attr) {
        return std::any_of(right.begin(), right.end(), [&](const auto& other) {
            return attr.first == other.first && attr.second == other.second;
        });
    });
}

bool excludes(const ExcludeSet& set, std::string_view type) {
    return set.all || std::find(set.names.begin(), set.names.end(), type) != set.names.end();
}

}  // namespace

bool attr_reads_string(const AttrSpec& spec) {
    return spec.rule == AttrRule::InfoStr || spec.rule == AttrRule::Align ||
           (spec.rule == AttrRule::Str && spec.choices);
}

void check_attr_value(const AttrInput& value, const AttrSpec& spec, const PathStack& path) {
    auto expected = [&](const char* what) {
        throw InvalidNodeError("invalid_attr_value", spec.name, "attr '" + spec.name + "' must be " + what,
                               format_path(path));
    };
    auto unrepresentable = [&](const char* why) {
        throw InvalidNodeError("unrepresentable", spec.name,
                               "attr '" + spec.name + "' cannot be expressed in markdown: " + why, format_path(path));
    };

    const long long* number = std::get_if<long long>(&value);
    switch (spec.rule) {
        case AttrRule::Str:
            if (!std::holds_alternative<std::string>(value)) {
                expected("a str");
            }
            break;
        case AttrRule::InfoStr:
            if (!std::holds_alternative<std::string>(value)) {
                expected("a str");
            }
            if (std::get<std::string>(value).find_first_of("\r\n") != std::string::npos) {
                expected("a single line");
            }
            break;
        case AttrRule::Bool:
            if (!std::holds_alternative<bool>(value)) {
                expected("a bool");
            }
            break;
        case AttrRule::Int:
            if (number == nullptr) {
                expected("an int");
            }
            break;
        case AttrRule::Level:
            if (number == nullptr || *number < 1 || *number > 6) {
                expected("an int between 1 and 6");
            }
            break;
        case AttrRule::ListStart:
            if (number == nullptr || *number < 0 || *number > kMaxListStart) {
                expected("an int between 0 and 999999999");
            }
            break;
        case AttrRule::Count:
            if (number == nullptr || *number < 0) {
                expected("a non-negative int");
            }
            break;
        case AttrRule::Align:
            if (std::holds_alternative<std::monostate>(value)) {
                break;
            }
            if (!std::holds_alternative<std::string>(value)) {
                expected("'left', 'center', 'right' or None");
            }
            {
                const std::string& align = std::get<std::string>(value);
                if (align != "left" && align != "center" && align != "right") {
                    expected("'left', 'center', 'right' or None");
                }
            }
            break;
        case AttrRule::Size:
            if (!std::holds_alternative<std::string>(value) && number == nullptr &&
                !std::holds_alternative<OverflowInt>(value)) {
                expected("a str or an int");
            }
            break;
        case AttrRule::ColWidth:
            if (!std::holds_alternative<std::vector<long long>>(value)) {
                expected("a list of ints");
            }
            break;
        case AttrRule::NoSpan:
            if (number == nullptr) {
                expected("an int");
            }
            if (*number != 1) {
                unrepresentable("GFM tables have no cell spanning");
            }
            break;
    }

    if (spec.choices) {
        if (std::none_of(spec.choices->begin(), spec.choices->end(), [&](const AttrValue& choice) {
                if (choice.kind == AttrValue::Kind::String) {
                    return std::get<std::string>(value) == choice.string_value;
                }
                if (choice.kind == AttrValue::Kind::Int) {
                    return std::get<long long>(value) == choice.int_value;
                }
                return std::get<bool>(value) == choice.bool_value;
            })) {
            expected("one of the declared choices");
        }
    }
}

void check_mark_set(const std::vector<Mark>& existing, const Mark& mark, const Schema& schema,
                    const PathStack& path) {
    if (existing.empty()) {
        return;
    }
    const MarkSpec& spec = *schema.mark(mark.type);
    for (const Mark& earlier : existing) {
        const MarkSpec& earlier_spec = *schema.mark(earlier.type);
        bool same_type = earlier.type == mark.type;
        if ((same_type && equal_attrs(earlier.attrs, mark.attrs)) || excludes(spec.excludes, earlier.type) ||
            excludes(earlier_spec.excludes, mark.type)) {
            std::string message = same_type
                                      ? "mark type '" + mark.type + "' conflicts with an earlier mark of the same type"
                                      : "mark type '" + mark.type +
                                            "' conflicts with earlier mark type '" + earlier.type + "'";
            throw InvalidNodeError("invalid_mark_set", "marks", std::move(message), format_path(path));
        }
    }
}

}  // namespace marktip
