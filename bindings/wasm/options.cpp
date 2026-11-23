#include "options.h"

#include <string>

namespace marktip::wasm {
namespace {

void check_option_names(JsonInput::Value options, bool from_dict) {
    for (auto item : JsonInput::items(options)) {
        std::string name = JsonInput::string(item.first);
        bool common = name == "linkSchemes" || name == "imageSchemes" || name == "linkRelative" ||
                      name == "imageRelative" || name == "rejectNodeTypes" || name == "cjkFriendly";
        bool specific = from_dict ? name == "strict" : name == "html" || name == "partial" || name == "keepSource";
        if (!common && !specific) {
            throw TypeError("unknown option '" + name + "'");
        }
    }
}

bool boolean_option(JsonInput::Value options, const char* name, bool fallback) {
    auto value = JsonInput::lookup(options, name);
    if (!value) {
        return fallback;
    }
    if (!JsonInput::is_bool(*value)) {
        throw TypeError(std::string(name) + " must be a bool");
    }
    return JsonInput::boolean(*value);
}

std::string string_option(JsonInput::Value options, const char* name, const char* fallback) {
    auto value = JsonInput::lookup(options, name);
    if (!value) {
        return fallback;
    }
    if (!JsonInput::is_str(*value)) {
        throw TypeError(std::string(name) + " must be a str");
    }
    return JsonInput::string(*value);
}

void schemes(JsonInput::Value options, const char* name, UriRule& rule) {
    auto value = JsonInput::lookup(options, name);
    if (!value || JsonInput::is_null(*value)) {
        return;
    }
    if (!JsonInput::is_list(*value)) {
        throw TypeError(std::string(name) + " must be an array of str");
    }
    rule.restrict_schemes = true;
    for (auto item : JsonInput::elements(*value)) {
        if (!JsonInput::is_str(item)) {
            throw TypeError(std::string(name) + " entries must be str");
        }
        add_uri_scheme(rule, JsonInput::string(item), name);
    }
}

void rejected_nodes(JsonInput::Value options, const Schema& schema, NodeTypePolicy& policy) {
    auto value = JsonInput::lookup(options, "rejectNodeTypes");
    if (!value || JsonInput::is_null(*value)) {
        return;
    }
    if (!JsonInput::is_list(*value)) {
        throw TypeError("rejectNodeTypes must be an array of str");
    }
    for (auto item : JsonInput::elements(*value)) {
        if (!JsonInput::is_str(item)) {
            throw TypeError("rejectNodeTypes entries must be str");
        }
        add_rejected_node_type(policy, JsonInput::string(item), schema, "rejectNodeTypes");
    }
}

}  // namespace

ConversionOptions read_options(JsonInput::Value value, const Schema& schema, bool from_dict) {
    if (!JsonInput::is_dict(value)) {
        throw TypeError("options must be an object");
    }
    check_option_names(value, from_dict);
    ConversionOptions options;
    schemes(value, "linkSchemes", options.uri.link);
    schemes(value, "imageSchemes", options.uri.image);
    options.uri.link.relative = relative_policy_from_string(string_option(value, "linkRelative", "allow"),
                                                            "linkRelative");
    options.uri.image.relative = relative_policy_from_string(string_option(value, "imageRelative", "allow"),
                                                             "imageRelative");
    rejected_nodes(value, schema, options.nodes);
    options.parser.cjk_friendly = boolean_option(value, "cjkFriendly", false);
    if (from_dict) {
        options.strict = strict_mode_from_string(string_option(value, "strict", "off"), "strict");
    } else {
        options.parser.html = boolean_option(value, "html", true);
        options.parser.partial = boolean_option(value, "partial", false);
        options.parser.keep_source = boolean_option(value, "keepSource", true);
    }
    return options;
}

}  // namespace marktip::wasm
