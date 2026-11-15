#pragma once

#include <string>
#include <string_view>

#include "json.h"

namespace marktip::wasm {

struct JsonOutput {
    struct Object {
        std::string& text;
        bool first = true;
    };
    using Array = Object;
    using Result = std::string;

    static void separator(Object& object) {
        if (!object.first) object.text.push_back(',');
        object.first = false;
    }

    static void key(Object& object, std::string_view name) {
        separator(object);
        append_json_string(object.text, name);
        object.text.push_back(':');
    }

    template <typename Fill>
    static Result object(Fill&& fill) {
        Result result = "{";
        Object context {result};
        fill(context);
        result.push_back('}');
        return result;
    }

    static void field(Object& object, std::string_view name, const std::string& value) {
        key(object, name);
        append_json_string(object.text, value);
    }

    static void field(Object& object, std::string_view name, long long value) {
        key(object, name);
        object.text += std::to_string(value);
    }

    static void field(Object& object, std::string_view name, bool value) {
        key(object, name);
        object.text += value ? "true" : "false";
    }

    template <typename Fill>
    static void field_object(Object& parent, std::string_view name, Fill&& fill) {
        key(parent, name);
        parent.text.push_back('{');
        Object child {parent.text};
        fill(child);
        parent.text.push_back('}');
    }

    template <typename Fill>
    static void field_array(Object& parent, std::string_view name, Fill&& fill) {
        key(parent, name);
        parent.text.push_back('[');
        Array child {parent.text};
        fill(child);
        parent.text.push_back(']');
    }

    template <typename Fill>
    static void append_object(Array& parent, Fill&& fill) {
        separator(parent);
        parent.text.push_back('{');
        Object child {parent.text};
        fill(child);
        parent.text.push_back('}');
    }

    static void append_integer(Array& array, long long value) {
        separator(array);
        array.text += std::to_string(value);
    }
};

}  // namespace marktip::wasm
