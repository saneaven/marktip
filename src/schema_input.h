#pragma once

#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "schema_builder.h"

namespace marktip {

// Input defines Value and static is_dict, is_list, is_str, is_bool, is_int and is_null predicates.
// is_int excludes booleans; lookup is called only on a value that passed is_dict.
// lookup(dict, key) returns optional<Value>, distinguishing an absent key from a present null.
// items(dict) yields entries with first as the key and second as the value; elements(list) yields Value items.
// string(value) and boolean(value) extract checked values; integer(value, long long&) returns false on overflow.
// type_error(message) raises the host type error and does not return.
template <typename Input>
class SchemaDeclarationReader {
    using Value = typename Input::Value;

    static void expect_dict(Value value, const char* field) {
        if (!Input::is_dict(value)) {
            Input::type_error(std::string(field) + " must be a dict");
        }
    }

    static void expect_list(Value value, const char* field) {
        if (!Input::is_list(value)) {
            Input::type_error(std::string(field) + " must be a list");
        }
    }

    static std::string string(Value value, const char* field) {
        if (!Input::is_str(value)) {
            Input::type_error(std::string(field) + " must be a str");
        }
        return Input::string(value);
    }

    static std::string required_string(Value object, const char* key, const char* field) {
        auto value = Input::lookup(object, key);
        if (!value) {
            Input::type_error(std::string(field) + " must be a str");
        }
        return string(*value, field);
    }

    static std::optional<std::string> optional_string(Value object, const char* field) {
        auto value = Input::lookup(object, field);
        if (!value || Input::is_null(*value)) {
            return std::nullopt;
        }
        return string(*value, field);
    }

    static bool boolean(Value object, const char* field) {
        auto value = Input::lookup(object, field);
        if (!value) {
            return false;
        }
        if (!Input::is_bool(*value)) {
            Input::type_error(std::string(field) + " must be a bool");
        }
        return Input::boolean(*value);
    }

    static long long integer(Value value) {
        long long number;
        if (!Input::integer(value, number)) {
            throw std::invalid_argument("declaration integer must fit in long long");
        }
        return number;
    }

    static AttrValue attr_value(Value value) {
        if (Input::is_bool(value)) {
            return AttrValue::boolean(Input::boolean(value));
        }
        if (Input::is_int(value)) {
            return AttrValue::integer(integer(value));
        }
        if (Input::is_str(value)) {
            return AttrValue::string(Input::string(value));
        }
        if (Input::is_list(value)) {
            std::vector<long long> numbers;
            for (Value item : Input::elements(value)) {
                if (!Input::is_int(item)) {
                    throw std::invalid_argument("IntList declaration values must be lists of ints");
                }
                numbers.push_back(integer(item));
            }
            return AttrValue::int_list(std::move(numbers));
        }
        throw std::invalid_argument("declaration values must be str, int, bool or IntList");
    }

    static AttrRule attr_rule(Value object) {
        auto value = Input::lookup(object, "type");
        if (value && Input::is_str(*value)) {
            std::string name = Input::string(*value);
            if (name == "str") return AttrRule::Str;
            if (name == "int") return AttrRule::Int;
            if (name == "bool") return AttrRule::Bool;
            if (name == "IntList") return AttrRule::ColWidth;
        }
        throw std::invalid_argument("attr type must be 'str', 'int', 'bool' or 'IntList'");
    }

    static std::vector<AttrDeclaration> attrs(Value object) {
        auto values = Input::lookup(object, "attrs");
        return values ? attr_items(*values) : std::vector<AttrDeclaration> {};
    }

    static std::vector<AttrDeclaration> attr_items(Value values) {
        expect_dict(values, "attrs");
        std::vector<AttrDeclaration> result;
        for (auto item : Input::items(values)) {
            AttrDeclaration attr;
            attr.name = string(item.first, "attr name");
            expect_dict(item.second, "attr declaration");
            attr.rule = attr_rule(item.second);
            attr.required = boolean(item.second, "required");
            auto choices = Input::lookup(item.second, "choices");
            if (choices && !Input::is_null(*choices)) {
                expect_list(*choices, "choices");
                attr.choices.emplace();
                for (Value choice : Input::elements(*choices)) {
                    attr.choices->push_back(attr_value(choice));
                }
            }
            auto fallback = Input::lookup(item.second, "default");
            if (fallback && !Input::is_null(*fallback)) {
                attr.fallback = attr_value(*fallback);
            }
            attr.uri = optional_string(item.second, "uri");
            attr.inherit = boolean(item.second, "inherit");
            result.push_back(std::move(attr));
        }
        return result;
    }

    static std::vector<MarkDeclaration> marks(Value values) {
        expect_list(values, "marks");
        std::vector<MarkDeclaration> result;
        for (Value value : Input::elements(values)) {
            expect_dict(value, "mark declaration");
            MarkDeclaration mark;
            mark.name = required_string(value, "name", "mark name");
            mark.tag = optional_string(value, "tag");
            mark.attrs = attrs(value);
            auto excludes = Input::lookup(value, "excludes");
            if (excludes && !Input::is_null(*excludes)) {
                if (Input::is_str(*excludes)) {
                    mark.excludes = Input::string(*excludes);
                } else {
                    expect_list(*excludes, "excludes");
                    std::vector<std::string> names;
                    for (Value name : Input::elements(*excludes)) {
                        names.push_back(string(name, "excludes entries"));
                    }
                    mark.excludes = std::move(names);
                }
            }
            result.push_back(std::move(mark));
        }
        return result;
    }

    static std::vector<NodeDeclaration> nodes(Value values) {
        expect_list(values, "nodes");
        std::vector<NodeDeclaration> result;
        for (Value value : Input::elements(values)) {
            expect_dict(value, "node declaration");
            NodeDeclaration node;
            node.name = required_string(value, "name", "node name");
            node.kind = required_string(value, "kind", "kind");
            node.content = optional_string(value, "content");
            node.group = optional_string(value, "group");
            node.tag = optional_string(value, "tag");
            node.attrs = attrs(value);
            node.implicit = boolean(value, "implicit");
            node.fence = optional_string(value, "fence");
            node.math = optional_string(value, "math");
            node.body = optional_string(value, "body");
            result.push_back(std::move(node));
        }
        return result;
    }

    static std::vector<CoreAttrDeclaration> core_attrs(Value values) {
        expect_dict(values, "core_attrs");
        std::vector<CoreAttrDeclaration> result;
        for (auto owner : Input::items(values)) {
            result.push_back({string(owner.first, "core attr type"), attr_items(owner.second)});
        }
        return result;
    }

public:
    static std::shared_ptr<Schema> read(Value declaration) {
        expect_dict(declaration, "schema declaration");
        auto mark_values = Input::lookup(declaration, "marks");
        auto node_values = Input::lookup(declaration, "nodes");
        auto core_values = Input::lookup(declaration, "core_attrs");
        std::vector<MarkDeclaration> mark_declarations = mark_values ? marks(*mark_values)
                                                                   : std::vector<MarkDeclaration> {};
        std::vector<NodeDeclaration> node_declarations = node_values ? nodes(*node_values)
                                                                   : std::vector<NodeDeclaration> {};
        std::vector<CoreAttrDeclaration> core_declarations = core_values ? core_attrs(*core_values)
                                                                      : std::vector<CoreAttrDeclaration> {};
        return SchemaBuilder::build(std::move(mark_declarations), std::move(node_declarations),
                                     std::move(core_declarations), boolean(declaration, "block_image"));
    }
};

}  // namespace marktip
