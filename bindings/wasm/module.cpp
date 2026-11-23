#include <emscripten/emscripten.h>

#include <cstddef>
#include <cstdint>
#include <exception>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>

#include "document_input.h"
#include "document_output.h"
#include "errors.h"
#include "input.h"
#include "json.h"
#include "options.h"
#include "output.h"
#include "schema_input.h"
#include "serializer.h"

namespace {

using namespace marktip;
using namespace marktip::wasm;

std::unordered_map<std::uint32_t, std::shared_ptr<const Schema>> schemas;
std::unordered_map<std::uint32_t, Document> documents;
std::uint32_t next_schema = 1;
std::uint32_t next_document = 1;
std::string result;
std::string error;

void error_field(const char* key, std::string_view value) {
    error += ',';
    append_json_string(error, key);
    error += ':';
    append_json_string(error, value);
}

void start_error(const char* name, const std::exception& exception) {
    error = "{\"name\":";
    append_json_string(error, name);
    error_field("message", exception.what());
}

void marktip_fields(const MarktipError& exception) {
    error_field("code", exception.code());
    error_field("path", exception.path());
    error_field("detail", exception.what());
}

template <typename Function>
std::uint32_t invoke(Function&& function) noexcept {
    result.clear();
    error.clear();
    try {
        return function();
    } catch (const UnknownTypeError& exception) {
        start_error("UnknownTypeError", exception);
        marktip_fields(exception);
        error_field("type", exception.type_name());
        error_field("kind", exception.kind());
    } catch (const InvalidNodeError& exception) {
        start_error("InvalidNodeError", exception);
        marktip_fields(exception);
        error_field("field", exception.field());
    } catch (const ParseError& exception) {
        start_error("ParseError", exception);
        marktip_fields(exception);
    } catch (const MarktipError& exception) {
        start_error("MarktipError", exception);
        marktip_fields(exception);
    } catch (const TypeError& exception) {
        start_error("TypeError", exception);
    } catch (const std::invalid_argument& exception) {
        start_error("RangeError", exception);
    } catch (const std::exception& exception) {
        start_error("Error", exception);
    }
    error += '}';
    return 0;
}

std::shared_ptr<const Schema> select_schema(std::uint32_t handle) {
    return handle == 0 ? Schema::gfm() : schemas.at(handle);
}

std::uint32_t retain(Document document) {
    std::uint32_t handle = next_document++;
    documents.emplace(handle, std::move(document));
    return handle;
}

JsonInput::Value root_dict(const JsonDocument& data) {
    auto value = data.root();
    if (!JsonInput::is_dict(value)) {
        throw TypeError("document must be an object");
    }
    return value;
}

}  // namespace

extern "C" {

EMSCRIPTEN_KEEPALIVE std::uint32_t mt_schema_new(const char* data, std::size_t length) {
    return invoke([&] {
        JsonDocument declaration(std::string_view(data, length));
        auto schema = SchemaDeclarationReader<JsonInput>::read(declaration.root());
        std::uint32_t handle = next_schema++;
        schemas.emplace(handle, std::move(schema));
        return handle;
    });
}

EMSCRIPTEN_KEEPALIVE std::uint32_t mt_from_markdown(const char* markdown, std::size_t length,
                                const char* options_data, std::size_t options_length, std::uint32_t schema_handle) {
    return invoke([&] {
        JsonDocument options_json(std::string_view(options_data, options_length));
        auto schema = select_schema(schema_handle);
        ConversionOptions options = read_options(options_json.root(), *schema, false);
        Document document = parse_to_document(std::string(markdown, length), options.parser, std::move(schema));
        finalize_document(document, options.nodes, options.uri, options.parser.cjk_friendly);
        return retain(std::move(document));
    });
}

EMSCRIPTEN_KEEPALIVE std::uint32_t mt_from_dict(const char* data, std::size_t length, const char* options_data,
                            std::size_t options_length, std::uint32_t schema_handle, std::uint32_t base_handle) {
    return invoke([&] {
        JsonDocument input(std::string_view(data, length));
        JsonDocument options_json(std::string_view(options_data, options_length));
        auto schema = select_schema(schema_handle);
        ConversionOptions options = read_options(options_json.root(), *schema, true);
        const Document* base = base_handle == 0 ? nullptr : &documents.at(base_handle);
        return retain(DocumentReader<JsonInput>::from_dict(root_dict(input), std::move(schema), options.strict, base)
                          .finish(options.nodes, options.uri));
    });
}

EMSCRIPTEN_KEEPALIVE std::uint32_t mt_load(const char* data, std::size_t length, std::uint32_t schema_handle) {
    return invoke([&] {
        auto schema = select_schema(schema_handle);
        JsonDocument input(std::string_view(data, length));
        return retain(DocumentReader<JsonInput>::load(root_dict(input), std::move(schema)));
    });
}

EMSCRIPTEN_KEEPALIVE void mt_to_dict(std::uint32_t handle) {
    invoke([&] {
        result = DocumentWriter<JsonOutput>::to_dict(documents.at(handle));
        return 0;
    });
}

EMSCRIPTEN_KEEPALIVE void mt_dump(std::uint32_t handle) {
    invoke([&] {
        result = DocumentWriter<JsonOutput>::dump(documents.at(handle));
        return 0;
    });
}

EMSCRIPTEN_KEEPALIVE void mt_to_markdown(std::uint32_t handle, int canonical) {
    invoke([&] {
        result = to_markdown(documents.at(handle), canonical != 0);
        return 0;
    });
}

EMSCRIPTEN_KEEPALIVE void mt_document_free(std::uint32_t handle) {
    invoke([&] {
        documents.erase(handle);
        return 0;
    });
}

EMSCRIPTEN_KEEPALIVE void mt_schema_free(std::uint32_t handle) {
    invoke([&] {
        schemas.erase(handle);
        return 0;
    });
}

EMSCRIPTEN_KEEPALIVE void mt_version() {
    invoke([] {
        result = MARKTIP_VERSION;
        return 0;
    });
}

EMSCRIPTEN_KEEPALIVE const char* mt_result_ptr() noexcept { return result.data(); }
EMSCRIPTEN_KEEPALIVE std::size_t mt_result_len() noexcept { return result.size(); }
EMSCRIPTEN_KEEPALIVE const char* mt_error_ptr() noexcept { return error.data(); }
EMSCRIPTEN_KEEPALIVE std::size_t mt_error_len() noexcept { return error.size(); }

}  // extern "C"
