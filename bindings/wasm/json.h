#pragma once

#include <stdexcept>
#include <string>
#include <string_view>

#include "yyjson.h"

namespace marktip::wasm {

inline void append_json_string(std::string& out, std::string_view value) {
    constexpr char digits[] = "0123456789abcdef";
    out.push_back('"');
    for (unsigned char ch : value) {
        switch (ch) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (ch < 0x20) {
                    out += "\\u00";
                    out.push_back(digits[ch >> 4]);
                    out.push_back(digits[ch & 15]);
                } else {
                    out.push_back(static_cast<char>(ch));
                }
                break;
        }
    }
    out.push_back('"');
}

// JsonDocument reads numbers as raw tokens, retaining their JSON spelling and numeric kind.
inline void append_json_literal(std::string& out, yyjson_val* value) {
    if (yyjson_is_str(value)) {
        append_json_string(out, {yyjson_get_str(value), yyjson_get_len(value)});
    } else if (yyjson_is_raw(value)) {
        out.append(yyjson_get_raw(value), yyjson_get_len(value));
    } else if (yyjson_is_null(value)) {
        out += "null";
    } else if (yyjson_is_bool(value)) {
        out += yyjson_get_bool(value) ? "true" : "false";
    } else if (yyjson_is_arr(value)) {
        out.push_back('[');
        yyjson_arr_iter iterator = yyjson_arr_iter_with(value);
        bool first = true;
        while (yyjson_val* child = yyjson_arr_iter_next(&iterator)) {
            if (!first) out.push_back(',');
            first = false;
            append_json_literal(out, child);
        }
        out.push_back(']');
    } else {
        out.push_back('{');
        yyjson_obj_iter iterator = yyjson_obj_iter_with(value);
        bool first = true;
        while (yyjson_val* key = yyjson_obj_iter_next(&iterator)) {
            if (!first) out.push_back(',');
            first = false;
            append_json_string(out, {yyjson_get_str(key), yyjson_get_len(key)});
            out.push_back(':');
            append_json_literal(out, yyjson_obj_iter_get_val(key));
        }
        out.push_back('}');
    }
}

class JsonDocument {
public:
    explicit JsonDocument(std::string_view source) {
        yyjson_read_err error {};
        document_ = yyjson_read_opts(const_cast<char*>(source.data()), source.size(),
                                     YYJSON_READ_NUMBER_AS_RAW, nullptr, &error);
        if (document_ == nullptr) {
            throw std::invalid_argument("invalid JSON at byte " + std::to_string(error.pos) + ": " + error.msg);
        }
    }

    ~JsonDocument() { yyjson_doc_free(document_); }
    JsonDocument(const JsonDocument&) = delete;
    JsonDocument& operator=(const JsonDocument&) = delete;

    yyjson_val* root() const { return yyjson_doc_get_root(document_); }

private:
    yyjson_doc* document_;
};

}  // namespace marktip::wasm
