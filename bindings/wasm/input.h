#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <utility>

#include "errors.h"
#include "json.h"
#include "value.h"

namespace marktip::wasm {

struct JsonInput {
    using Value = yyjson_val*;

    static bool is_dict(Value value) { return yyjson_is_obj(value); }
    static bool is_list(Value value) { return yyjson_is_arr(value); }
    static bool is_str(Value value) { return yyjson_is_str(value); }
    static bool is_bool(Value value) { return yyjson_is_bool(value); }
    static bool is_null(Value value) { return yyjson_is_null(value); }
    static bool is_int(Value value) {
        if (!yyjson_is_raw(value)) return false;
        std::string_view token(yyjson_get_raw(value), yyjson_get_len(value));
        return token.find_first_of(".eE") == std::string_view::npos;
    }

    static std::optional<Value> lookup(Value object, const char* key) {
        Value value = yyjson_obj_get(object, key);
        return value == nullptr ? std::nullopt : std::optional<Value>(value);
    }

    struct Items {
        Value object;
        struct Iterator {
            yyjson_obj_iter state {};
            Value key = nullptr;

            Iterator() = default;
            explicit Iterator(Value object) : state(yyjson_obj_iter_with(object)) {
                key = yyjson_obj_iter_next(&state);
            }
            std::pair<Value, Value> operator*() const { return {key, yyjson_obj_iter_get_val(key)}; }
            Iterator& operator++() { key = yyjson_obj_iter_next(&state); return *this; }
            bool operator!=(const Iterator& other) const { return key != other.key; }
        };
        Iterator begin() const { return Iterator(object); }
        Iterator end() const { return Iterator(); }
    };

    struct Elements {
        Value array;
        struct Iterator {
            yyjson_arr_iter state {};
            Value value = nullptr;

            Iterator() = default;
            explicit Iterator(Value array) : state(yyjson_arr_iter_with(array)) {
                value = yyjson_arr_iter_next(&state);
            }
            Value operator*() const { return value; }
            Iterator& operator++() { value = yyjson_arr_iter_next(&state); return *this; }
            bool operator!=(const Iterator& other) const { return value != other.value; }
        };
        Iterator begin() const { return Iterator(array); }
        Iterator end() const { return Iterator(); }
    };

    static Items items(Value value) { return {value}; }
    static Elements elements(Value value) { return {value}; }
    static std::size_t size(Value value) { return yyjson_arr_size(value); }

    static std::string string(Value value) {
        if (!is_str(value)) throw TypeError("expected a string");
        return {yyjson_get_str(value), yyjson_get_len(value)};
    }

    static bool boolean(Value value) {
        if (!is_bool(value)) throw TypeError("expected a boolean");
        return yyjson_get_bool(value);
    }

    static bool integer(Value value, long long& result) {
        auto number = parse_decimal_int({yyjson_get_raw(value), yyjson_get_len(value)});
        if (!number) return false;
        result = *number;
        return true;
    }

    static std::string coerce_string(Value value) {
        if (is_str(value)) return string(value);
        std::string result;
        append_json_literal(result, value);
        return result;
    }

    [[noreturn]] static void type_error(const std::string& message) { throw TypeError(message); }
};

}  // namespace marktip::wasm
