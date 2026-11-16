#pragma once

#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "ast.h"
#include "compiler.h"
#include "inherit.h"
#include "policy.h"
#include "schema.h"
#include "validate.h"

namespace marktip {

// Input provides Value, type predicates and lookup(dict, key) -> optional<Value>, with absent distinct from null.
// from_dict and load require roots that already passed is_dict; lookup is called only on checked dicts.
// is_int excludes bools; integer(value, long long&) returns false on overflow; size reads a checked list.
// string and boolean may receive stored scalars of another type; conversion and failure follow the host.
// coerce_string receives non-null values, including numbers, bools, lists, dicts and dict keys.
// items yields entries with first/second as key/value; elements yields Value items.
template <typename Input>
class DocumentReader {
    using Value = typename Input::Value;

    static Value expect_dict(std::optional<Value> value, std::string_view context,
                              const char* field, const PathStack& path) {
        if (!value || !Input::is_dict(*value)) {
            throw InvalidNodeError("wrong_type", field, std::string(context) + " must be a dict", format_path(path));
        }
        return *value;
    }

    static Value expect_list(std::optional<Value> value, std::string_view context,
                              const char* field, const PathStack& path) {
        if (!value || !Input::is_list(*value)) {
            throw InvalidNodeError("wrong_type", field, std::string(context) + " must be a list", format_path(path));
        }
        return *value;
    }

    static std::string to_string(std::optional<Value> value) {
        if (!value || Input::is_null(*value)) {
            return "";
        }
        return Input::coerce_string(*value);
    }

    static std::string required_type(Value value, std::string_view context, const PathStack& path) {
        auto type = Input::lookup(value, "type");
        check_type_present(type && !Input::is_null(*type), context, path);
        return to_string(type);
    }

    static std::optional<std::vector<long long>> int_list_from_input(Value values) {
        std::vector<long long> numbers;
        for (Value item : Input::elements(values)) {
            long long number = 0;
            if (!Input::is_int(item) || !Input::integer(item, number)) {
                return std::nullopt;
            }
            numbers.push_back(number);
        }
        return numbers;
    }

    static std::optional<StrMapEntries> str_map_from_input(Value values) {
        StrMapEntries entries;
        for (auto item : Input::items(values)) {
            if (!Input::is_str(item.first) || !Input::is_str(item.second)) {
                return std::nullopt;
            }
            std::string key = Input::string(item.first);
            if (!str_map_key(key)) {
                return std::nullopt;
            }
            entries.emplace_back(std::move(key), Input::string(item.second));
        }
        return entries;
    }

    // --- the attr schema --------------------------------------------------------
    //
    // Attr reading keeps the values Markdown can act on; strict mode checks the losses a caller refuses.

    // Scalars, declared int lists and declared string maps are values the serializer can act on;
    // every other key is dropped.
    // Stringifying unsupported values would store text the caller never wrote and lose the original value.
    // Null is omitted from AttrList.
    // The key sink keeps it distinct from an absent key for inheritance.
    static AttrList attrs_from_input(Value attrs, const std::vector<AttrSpec>& specs,
                                      std::vector<std::string>* keys = nullptr) {
        AttrList out;
        for (auto item : Input::items(attrs)) {
            std::string name = to_string(item.first);
            if (keys != nullptr) {
                keys->push_back(name);
            }
            Value value = item.second;
            bool is_bool = Input::is_bool(value);
            bool is_int = !is_bool && Input::is_int(value);
            if (!is_bool && !is_int && !Input::is_str(value)) {
                if (Input::is_list(value) && attr_stores_int_list(specs, name)) {
                    auto numbers = int_list_from_input(value);
                    if (numbers) {
                        store_attr(out, std::move(name), AttrValue::int_list(std::move(*numbers)), specs);
                    }
                } else if (Input::is_dict(value) && attr_stores_str_map(specs, name)) {
                    auto entries = str_map_from_input(value);
                    if (entries) {
                        store_attr(out, std::move(name), AttrValue::str_map(std::move(*entries)), specs);
                    }
                }
                continue;
            }
            long long number = 0;
            if (is_int && !Input::integer(value, number)) {
                continue;
            }
            AttrValue attr = is_bool ? AttrValue::boolean(Input::boolean(value)) :
                             is_int ? AttrValue::integer(number) :
                                      AttrValue::string(Input::string(value));
            store_attr(out, std::move(name), std::move(attr), specs);
        }
        return out;
    }

    // Types are always closed; strict mode also closes fields, content models and attrs.
    // Content and Exact differ over attrs whose Markdown form is Dropped.
    // Check raw attrs before conversion, which omits nulls and values the writer cannot carry.

    static void check_top_level_fields(Value value, std::string_view owner_type, const char* kind,
                                        bool inline_type, const PathStack& path) {
        for (auto item : Input::items(value)) {
            check_top_level_field(to_string(item.first), owner_type, kind, inline_type, path);
        }
    }

    static void check_text_payload_input(Value node_dict, const PathStack& path) {
        auto value = Input::lookup(node_dict, "text");
        bool is_string = value && Input::is_str(*value);
        std::string text = is_string ? Input::string(*value) : std::string{};
        check_text_payload(value.has_value(), is_string, text, path);
    }

    static AttrInput attr_input_from_input(Value value, const AttrSpec& spec) {
        if (Input::is_null(value)) {
            return std::monostate{};
        }
        if (Input::is_bool(value)) {
            return Input::boolean(value);
        }
        if (Input::is_int(value)) {
            long long number = 0;
            if (Input::integer(value, number)) {
                return number;
            }
            return OverflowInt{};
        }
        if (Input::is_str(value)) {
            // Type-only rules must reject a wrong-type string before UTF-8 encoding can fail on a lone surrogate.
            if (attr_reads_string(spec)) {
                return Input::string(value);
            }
            return std::string{};
        }
        if (attr_reads_int_list(spec) && Input::is_list(value)) {
            auto numbers = int_list_from_input(value);
            return numbers ? AttrInput(std::move(*numbers)) : AttrInput(OtherValue{});
        }
        if (attr_reads_str_map(spec) && Input::is_dict(value)) {
            auto entries = str_map_from_input(value);
            return entries ? AttrInput(std::move(*entries)) : AttrInput(OtherValue{});
        }
        return OtherValue{};
    }

    static void check_attrs_strict(Value attrs, const std::vector<AttrSpec>& specs, std::string_view owner_type,
                                    const char* kind, StrictMode mode, const PathStack& path) {
        for (auto item : Input::items(attrs)) {
            std::string name = to_string(item.first);
            const AttrSpec* spec = check_attr_name(specs, name, Input::is_null(item.second),
                                                   owner_type, kind, mode, path);
            if (spec != nullptr) {
                check_attr_value(attr_input_from_input(item.second, *spec), *spec, path);
            }
        }
    }

    static Mark mark_from_input(Value mark_dict, const Schema& schema, StrictMode mode, const PathStack& path,
                                 std::vector<std::string>* keys) {
        Mark mark;
        mark.type = required_type(mark_dict, "mark", path);
        const MarkSpec* spec = require_mark_spec(schema, mark.type, path);
        if (mode != StrictMode::Off) {
            check_top_level_fields(mark_dict, mark.type, "mark", false, path);
        }

        const std::vector<AttrSpec>& specs = spec->attrs;
        auto attrs = Input::lookup(mark_dict, "attrs");
        if (attrs && (!Input::is_null(*attrs) || mode != StrictMode::Off)) {
            Value attr_dict = expect_dict(attrs, "mark attrs", "attrs", path);
            if (mode != StrictMode::Off) {
                check_attrs_strict(attr_dict, specs, mark.type, "mark", mode, path);
            }
            mark.attrs = attrs_from_input(attr_dict, specs, keys);
        }
        // Outside the block above: a link with no attrs key still has no destination.
        if (mode != StrictMode::Off) {
            check_required_attrs(mark.attrs, specs, mark.type, "mark", path);
        }

        return mark;
    }

    // Keep mark parsing outside fill_node_from_input's recursive frame.
    // kMaxNodeDepth must remain safe on the smaller Windows worker stack even as strict checks grow.
    static MARKTIP_NOINLINE void fill_marks_from_input(Node& node, std::optional<Value> marks, const Schema& schema,
                                                       StrictMode mode, PathStack& path, NodeAttrKeys* keys) {
        if (!marks || (Input::is_null(*marks) && mode == StrictMode::Off)) {
            return;
        }

        Value mark_list = expect_list(marks, "node marks", "marks", path);
        std::size_t mark_index = 0;
        for (Value mark_handle : Input::elements(mark_list)) {
            path.push_back({"marks", mark_index});
            std::vector<std::string>* mark_keys = nullptr;
            if (keys != nullptr) {
                keys->marks.emplace_back();
                mark_keys = &keys->marks.back();
            }
            Mark mark = mark_from_input(expect_dict(mark_handle, "mark", "marks", path), schema, mode, path, mark_keys);
            if (mode != StrictMode::Off) {
                check_mark_set(node.marks, mark, schema, path);
            }
            node.marks.push_back(std::move(mark));
            path.pop_back();
            ++mark_index;
        }
    }

    // Keep node field/attr/mark parsing outside fill_node_from_input's recursive frame.
    // kMaxNodeDepth must remain safe on small Windows worker stacks even as strict validation grows.
    static MARKTIP_NOINLINE const NodeSpec* fill_node_fields_from_input(
        Document& document, std::size_t index, Value node_dict, std::string_view context,
        StrictMode mode, PathStack& path, NodeAttrKeys* keys) {
        Node node;
        node.type = required_type(node_dict, context, path);
        const Schema& schema = document.schema();
        const NodeSpec* spec = require_node_spec(schema, node.type, path);

        if (mode != StrictMode::Off) {
            check_top_level_fields(node_dict, node.type, "node", node_allows_marks(*spec), path);
            if (node.type == "text") {
                check_text_payload_input(node_dict, path);
            }
        }

        if (node.type == "text") {
            node.text = normalize_content_string(to_string(Input::lookup(node_dict, "text")));
        }

        const std::vector<AttrSpec>& specs = spec->attrs;
        auto attrs = Input::lookup(node_dict, "attrs");
        if (attrs && (!Input::is_null(*attrs) || mode != StrictMode::Off)) {
            Value attr_dict = expect_dict(attrs, "node attrs", "attrs", path);
            if (mode != StrictMode::Off) {
                check_attrs_strict(attr_dict, specs, node.type, "node", mode, path);
            }
            node.attrs = attrs_from_input(attr_dict, specs, keys != nullptr ? &keys->node : nullptr);
        }
        // Outside the block above: an image with no attrs key at all still has no src.
        if (mode != StrictMode::Off) {
            check_required_attrs(node.attrs, specs, node.type, "node", path);
            check_raw_carriers(node, schema, path);
        }

        auto marks = Input::lookup(node_dict, "marks");
        fill_marks_from_input(node, marks, schema, mode, path, keys);
        if (mode != StrictMode::Off && !spec->core) {
            check_node_marks(node, *spec, path);
        }

        document.node(index) = std::move(node);
        return spec;
    }

    static const NodeSpec* fill_node_from_input(Document& document, std::size_t index, Value node_dict,
                                                std::string_view context, std::size_t depth, StrictMode mode,
                                                PathStack& path, InputAttrKeys* keys = nullptr) {
        check_node_depth(depth, path);

        if (keys != nullptr) {
            keys->resize(index + 1);
        }
        const NodeSpec* spec = fill_node_fields_from_input(document, index, node_dict, context, mode, path,
                                                           keys != nullptr ? &(*keys)[index] : nullptr);

        auto content = Input::lookup(node_dict, "content");
        if (!content || (Input::is_null(*content) && mode == StrictMode::Off)) {
            if (mode != StrictMode::Off && !spec->core) {
                check_node_content(document, index, *spec, path);
            }
            return spec;
        }

        Value content_list = expect_list(content, "node content", "content", path);
        if (mode != StrictMode::Off) {
            check_content_field(*spec, path);
        }
        std::size_t child_pos = 0;
        for (Value child_handle : Input::elements(content_list)) {
            path.push_back({"content", child_pos});
            Value child_dict = expect_dict(child_handle, "content child", "content", path);
            std::size_t child_index = document.append_child(index, Node{});
            const NodeSpec* child = fill_node_from_input(document, child_index, child_dict, "node", depth + 1,
                                                         mode, path, keys);
            if (mode != StrictMode::Off) {
                check_child_content(document, *spec, *child, document.node(child_index),
                                    Input::size(content_list), path);
            }
            path.pop_back();
            ++child_pos;
        }
        if (mode != StrictMode::Off && !spec->core) {
            check_node_content(document, index, *spec, path);
        }
        return spec;
    }

public:
    static Document from_dict(Value root, std::shared_ptr<const Schema> selected_schema,
                               const NodeTypePolicy& node_policy, const UriPolicy& policy, StrictMode mode,
                               const Document* base = nullptr) {
        const Document* inheritance_base = base != nullptr &&
            base->schema().fingerprint() == selected_schema->fingerprint() ? base : nullptr;
        PathStack path;
        path.reserve(32);

        std::string type = required_type(root, "root node", path);
        check_root_type(type, path);

        Document document(std::move(selected_schema));
        if (inheritance_base != nullptr) {
            InputAttrKeys present;
            fill_node_from_input(document, 0, root, "root node", 0, mode, path, &present);
            inherit_attrs_and_spelling(document, *inheritance_base, present);
        } else {
            fill_node_from_input(document, 0, root, "root node", 0, mode, path);
        }
        finalize_document(document, node_policy, policy);
        return document;
    }

    static Document load(Value data, std::shared_ptr<const Schema> schema) {
        auto version = Input::lookup(data, "marktip");
        long long number = 0;
        if (!version || !Input::is_int(*version) || !Input::integer(*version, number) || number != 1) {
            throw std::invalid_argument("unsupported marktip version");
        }
        PathStack path;
        Value content = expect_dict(Input::lookup(data, "doc"), "stored document", "doc", path);
        Document document = from_dict(content, std::move(schema), NodeTypePolicy {}, UriPolicy {}, StrictMode::Off);
        auto source_value = Input::lookup(data, "source");
        if (!source_value) {
            return document;
        }
        if (Input::string(Input::lookup(data, "schema").value()) != document.schema().fingerprint()) {
            return document;
        }
        Value source = expect_dict(source_value, "stored source", "source", path);
        StoredSpelling stored;
        stored.head = Input::string(Input::lookup(source, "head").value());
        Value items = expect_list(Input::lookup(source, "items"), "stored items", "items", path);
        stored.items.reserve(Input::size(items));
        std::size_t blocks = 0;
        for (Value value : Input::elements(items)) {
            Value item = expect_dict(value, "stored item", "items", path);
            StoredPiece piece;
            if (auto text = Input::lookup(item, "text")) {
                piece.text = Input::string(*text);
            }
            piece.sep = Input::string(Input::lookup(item, "sep").value());
            auto node = Input::lookup(item, "node");
            piece.has_node = !node || Input::boolean(*node);
            blocks += piece.has_node;
            stored.items.push_back(std::move(piece));
        }
        if (blocks == document.root().content.size()) {
            document.spelling() = restore_spelling(stored);
        }
        return document;
    }
};

}  // namespace marktip
