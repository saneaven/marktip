#pragma once

#include <utility>

#include "ast.h"
#include "schema.h"
#include "serializer.h"

namespace marktip {

// Output provides Object, Array and Result types, and static operations that write fields in call order.
// object(fill) returns a root result; field takes const std::string&, std::string&&, long long or bool.
// Field keys are const char* or const std::string&.
// field_object, field_array and append_object invoke fill with a mutable child Object or Array context.
// append_integer writes an integer array item; callbacks complete synchronously and need not create host values.
template <typename Output>
class DocumentWriter {
    using Object = typename Output::Object;
    using Array = typename Output::Array;

    static void attrs(Object& out, const AttrList& values) {
        for (const auto& attr : values) {
            switch (attr.second.kind) {
                case AttrValue::Kind::String:
                    Output::field(out, attr.first, attr.second.string_value);
                    break;
                case AttrValue::Kind::Int:
                    Output::field(out, attr.first, attr.second.int_value);
                    break;
                case AttrValue::Kind::Bool:
                    Output::field(out, attr.first, attr.second.bool_value);
                    break;
                case AttrValue::Kind::IntList:
                    Output::field_array(out, attr.first, [&](Array& list) {
                        for (long long number : attr.second.int_list_value()) {
                            Output::append_integer(list, number);
                        }
                    });
                    break;
            }
        }
    }

    static void mark(Object& out, const Mark& value) {
        Output::field(out, "type", value.type);
        if (!value.attrs.empty()) {
            Output::field_object(out, "attrs", [&](Object& object) { attrs(object, value.attrs); });
        }
    }

    static void node(Object& out, const Document& document, std::size_t index) {
        const Node& value = document.node(index);
        Output::field(out, "type", value.type);

        if (value.type == "text") {
            Output::field(out, "text", value.text);
        }

        if (!value.attrs.empty()) {
            Output::field_object(out, "attrs", [&](Object& object) { attrs(object, value.attrs); });
        }

        if (!value.marks.empty()) {
            Output::field_array(out, "marks", [&](Array& list) {
                for (const Mark& value_mark : value.marks) {
                    Output::append_object(list, [&](Object& object) { mark(object, value_mark); });
                }
            });
        }

        if (value.type == "doc" || !value.content.empty()) {
            Output::field_array(out, "content", [&](Array& list) {
                for (std::size_t child : value.content) {
                    Output::append_object(list, [&](Object& object) { node(object, document, child); });
                }
            });
        }
    }

public:
    static typename Output::Result to_dict(const Document& document) {
        return Output::object([&](Object& out) { node(out, document, 0); });
    }

    static typename Output::Result dump(const Document& document) {
        return Output::object([&](Object& out) {
            Output::field(out, "marktip", 1LL);
            Output::field(out, "schema", document.schema().fingerprint());
            Output::field_object(out, "doc", [&](Object& object) { node(object, document, 0); });
            std::optional<StoredSpelling> stored = dump_spelling(document);
            if (stored) {
                Output::field_object(out, "source", [&](Object& source) {
                    Output::field(source, "head", std::move(stored->head));
                    Output::field_array(source, "items", [&](Array& items) {
                        for (StoredPiece& piece : stored->items) {
                            Output::append_object(items, [&](Object& item) {
                                if (piece.text) {
                                    Output::field(item, "text", std::move(*piece.text));
                                }
                                Output::field(item, "sep", std::move(piece.sep));
                                if (!piece.has_node) {
                                    Output::field(item, "node", false);
                                }
                            });
                        }
                    });
                });
            }
        });
    }
};

}  // namespace marktip
