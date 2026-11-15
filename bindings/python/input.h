#pragma once

#include <pybind11/pybind11.h>

#include <optional>
#include <string>

namespace marktip {

struct PythonInput {
    using Value = pybind11::handle;

    static bool is_dict(Value value) { return pybind11::isinstance<pybind11::dict>(value); }
    static bool is_list(Value value) { return pybind11::isinstance<pybind11::list>(value); }
    static bool is_str(Value value) { return pybind11::isinstance<pybind11::str>(value); }
    static bool is_bool(Value value) { return pybind11::isinstance<pybind11::bool_>(value); }
    static bool is_int(Value value) { return pybind11::isinstance<pybind11::int_>(value) && !is_bool(value); }
    static bool is_null(Value value) { return value.is_none(); }

    static std::optional<Value> lookup(Value dict, const char* key) {
        PyObject* value = PyDict_GetItemString(dict.ptr(), key);
        return value == nullptr ? std::nullopt : std::optional<Value>(Value(value));
    }

    static pybind11::dict items(Value value) { return pybind11::reinterpret_borrow<pybind11::dict>(value); }
    static pybind11::list elements(Value value) { return pybind11::reinterpret_borrow<pybind11::list>(value); }
    static std::size_t size(Value value) { return PyList_Size(value.ptr()); }
    static std::string string(Value value) { return pybind11::cast<std::string>(value); }
    static std::string coerce_string(Value value) { return pybind11::cast<std::string>(pybind11::str(value)); }
    static bool boolean(Value value) { return pybind11::cast<bool>(value); }

    static bool integer(Value value, long long& result) {
        int overflow = 0;
        result = PyLong_AsLongLongAndOverflow(value.ptr(), &overflow);
        if (overflow != 0 || (result == -1 && PyErr_Occurred() != nullptr)) {
            PyErr_Clear();
            return false;
        }
        return true;
    }

    [[noreturn]] static void type_error(const std::string& message) { throw pybind11::type_error(message); }
};

}  // namespace marktip
