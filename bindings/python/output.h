#pragma once

#include <pybind11/pybind11.h>

#include <string>
#include <utility>

namespace marktip {

struct PythonOutput {
    using Object = pybind11::dict;
    using Array = pybind11::list;
    using Result = pybind11::dict;

    template <typename Fill>
    static Result object(Fill&& fill) {
        Object result;
        fill(result);
        return result;
    }

    template <typename Value>
    static void field(Object& object, const char* key, Value&& value) {
        object[key] = std::forward<Value>(value);
    }

    template <typename Value>
    static void field(Object& object, const std::string& key, Value&& value) {
        object[pybind11::str(key)] = std::forward<Value>(value);
    }

    template <typename Key, typename Fill>
    static void field_object(Object& parent, const Key& key, Fill&& fill) {
        Object child;
        fill(child);
        field(parent, key, std::move(child));
    }

    template <typename Key, typename Fill>
    static void field_array(Object& parent, const Key& key, Fill&& fill) {
        Array child;
        fill(child);
        field(parent, key, std::move(child));
    }

    template <typename Fill>
    static void append_object(Array& parent, Fill&& fill) {
        Object child;
        fill(child);
        parent.append(std::move(child));
    }

    static void append_integer(Array& array, long long value) {
        array.append(value);
    }
};

}  // namespace marktip
