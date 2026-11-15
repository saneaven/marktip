#include "bindings.h"

#include "inherit.h"
#include "schema.h"
#include "serializer.h"

namespace py = pybind11;

namespace marktip {
namespace {

bool dict_contains(py::dict dict, const char* key) {
    return PyMapping_HasKeyString(dict.ptr(), key) == 1;
}

py::object dict_get(py::dict dict, const char* key) {
    if (!dict_contains(dict, key)) {
        return py::none();
    }
    return dict[py::str(key)];
}

py::dict expect_dict(py::handle value, std::string_view context, const char* field, const PathStack& path) {
    if (!py::isinstance<py::dict>(value)) {
        throw InvalidNodeError("wrong_type", field, std::string(context) + " must be a dict", format_path(path));
    }
    return py::reinterpret_borrow<py::dict>(value);
}

py::list expect_list(py::handle value, std::string_view context, const char* field, const PathStack& path) {
    if (!py::isinstance<py::list>(value)) {
        throw InvalidNodeError("wrong_type", field, std::string(context) + " must be a list", format_path(path));
    }
    return py::reinterpret_borrow<py::list>(value);
}

std::string py_to_string(py::handle value) {
    if (value.is_none()) {
        return "";
    }
    return py::cast<std::string>(py::str(value));
}

std::string required_type(py::dict value, std::string_view context, const PathStack& path) {
    py::object type = dict_get(value, "type");
    check_type_present(!type.is_none(), context, path);
    return py_to_string(type);
}

py::dict attrs_to_py(const AttrList& attrs) {
    py::dict out;
    for (const auto& attr : attrs) {
        switch (attr.second.kind) {
            case AttrValue::Kind::String:
                out[py::str(attr.first)] = attr.second.string_value;
                break;
            case AttrValue::Kind::Int:
                out[py::str(attr.first)] = attr.second.int_value;
                break;
            case AttrValue::Kind::Bool:
                out[py::str(attr.first)] = attr.second.bool_value;
                break;
            case AttrValue::Kind::IntList: {
                py::list values;
                for (long long number : attr.second.int_list_value()) {
                    values.append(number);
                }
                out[py::str(attr.first)] = std::move(values);
                break;
            }
        }
    }
    return out;
}

// Out-of-range values (10 ** 100) come back false rather than raising,
// so they report as a document problem with a path, not as an unlocated OverflowError.
bool as_int(py::handle value, long long& out) {
    int overflow = 0;
    long long result = PyLong_AsLongLongAndOverflow(value.ptr(), &overflow);
    if (overflow != 0 || (result == -1 && PyErr_Occurred() != nullptr)) {
        PyErr_Clear();
        return false;
    }
    out = result;
    return true;
}

// py::bool_ is a subclass of py::int_, so every integer rule has to exclude it first.
bool is_plain_int(py::handle value) {
    return py::isinstance<py::int_>(value) && !py::isinstance<py::bool_>(value);
}

std::optional<std::vector<long long>> int_list_from_py(py::list values) {
    std::vector<long long> numbers;
    for (py::handle item : values) {
        long long number = 0;
        if (!is_plain_int(item) || !as_int(item, number)) {
            return std::nullopt;
        }
        numbers.push_back(number);
    }
    return numbers;
}

// --- the attr schema --------------------------------------------------------
//
// Which attrs each type may carry, what each may hold, and what is lost by converting it.
// Two readers: attrs_from_py just below, which keeps the values markdown can act on,
// and strict mode further down, which decides which of the losses a caller is willing to take.

// Scalars and declared int lists are the values the serializer can act on; every other key is dropped.
// Stamping the rest through py::str turned [100] into "[100]" and a None into "",
// which put a string the caller never wrote into to_dict() and lost the value anyway.
// None is omitted from AttrList.
// The key sink keeps it distinct from an absent key for inheritance.
AttrList attrs_from_py(py::dict attrs, const std::vector<AttrSpec>& specs,
                       std::vector<std::string>* keys = nullptr) {
    AttrList out;
    for (auto item : attrs) {
        std::string name = py_to_string(item.first);
        if (keys != nullptr) {
            keys->push_back(name);
        }
        py::handle value = item.second;
        bool is_bool = py::isinstance<py::bool_>(value);
        bool is_int = !is_bool && py::isinstance<py::int_>(value);
        if (!is_bool && !is_int && !py::isinstance<py::str>(value)) {
            if (py::isinstance<py::list>(value) && attr_stores_int_list(specs, name)) {
                auto numbers = int_list_from_py(py::reinterpret_borrow<py::list>(value));
                if (numbers) {
                    store_attr(out, std::move(name), AttrValue::int_list(std::move(*numbers)), specs);
                }
            }
            continue;
        }
        AttrValue attr = is_bool ? AttrValue::boolean(py::cast<bool>(value)) :
                         is_int ? AttrValue::integer(py::cast<long long>(value)) :
                                  AttrValue::string(py::cast<std::string>(value));
        store_attr(out, std::move(name), std::move(attr), specs);
    }
    return out;
}

py::dict mark_to_py(const Mark& mark) {
    py::dict out;
    out["type"] = mark.type;
    if (!mark.attrs.empty()) {
        out["attrs"] = attrs_to_py(mark.attrs);
    }
    return out;
}

py::dict node_to_py(const Document& document, std::size_t index) {
    const Node& node = document.node(index);
    py::dict out;
    out["type"] = node.type;

    if (node.type == "text") {
        out["text"] = node.text;
    }

    if (!node.attrs.empty()) {
        out["attrs"] = attrs_to_py(node.attrs);
    }

    if (!node.marks.empty()) {
        py::list marks;
        for (const auto& mark : node.marks) {
            marks.append(mark_to_py(mark));
        }
        out["marks"] = marks;
    }

    if (node.type == "doc" || !node.content.empty()) {
        py::list content;
        for (std::size_t child : node.content) {
            content.append(node_to_py(document, child));
        }
        out["content"] = content;
    }

    return out;
}

// --- strict mode ------------------------------------------------------------
//
// Node and mark *types* are always closed, while strict additionally closes
// their top-level fields, content models and attrs. Without it, a field or attr
// the serializer never reads is dropped without a word.
// strict names what a caller refuses to lose, from the walk that is already
// happening, so a consumer does not have to re-traverse the tree in Python just
// to find out whether the document survives conversion intact.
//
// Content and Exact differ over one thing, the Dropped attrs,
// and they differ because nothing in the JSON says whether a `target: "_blank"` was chosen or stamped on:
// ProseMirror serializes schema defaults onto every node, so both spellings arrive identical.
// A caller storing markdown as the record wants Content; one keeping the JSON wants Exact.
//
// The attr check reads the raw py::dict rather than the built AttrList,
// because attrs_from_py has already dropped a None and anything it cannot carry by then.

void check_top_level_fields(py::dict value, std::string_view owner_type, const char* kind,
                            bool inline_type, const PathStack& path) {
    for (auto item : value) {
        check_top_level_field(py_to_string(item.first), owner_type, kind, inline_type, path);
    }
}

void check_text_payload_py(py::dict node_dict, const PathStack& path) {
    bool present = dict_contains(node_dict, "text");
    py::object value = present ? py::object(node_dict[py::str("text")]) : py::object(py::none());
    bool is_string = py::isinstance<py::str>(value);
    std::string text = is_string ? py::cast<std::string>(value) : std::string{};
    check_text_payload(present, is_string, text, path);
}

AttrInput attr_input_from_py(py::handle value, const AttrSpec& spec) {
    if (value.is_none()) {
        return std::monostate{};
    }
    if (py::isinstance<py::bool_>(value)) {
        return py::cast<bool>(value);
    }
    if (py::isinstance<py::int_>(value)) {
        long long number = 0;
        if (as_int(value, number)) {
            return number;
        }
        return OverflowInt{};
    }
    if (py::isinstance<py::str>(value)) {
        // Type-only rules must reject a wrong-type string before UTF-8 encoding can fail on a lone surrogate.
        if (attr_reads_string(spec)) {
            return py::cast<std::string>(value);
        }
        return std::string{};
    }
    if (attr_reads_int_list(spec) && py::isinstance<py::list>(value)) {
        auto numbers = int_list_from_py(py::reinterpret_borrow<py::list>(value));
        return numbers ? AttrInput(std::move(*numbers)) : AttrInput(OtherValue{});
    }
    return OtherValue{};
}

void check_attrs_strict(py::dict attrs, const std::vector<AttrSpec>& specs, std::string_view owner_type,
                        const char* kind, StrictMode mode, const PathStack& path) {
    for (auto item : attrs) {
        std::string name = py_to_string(item.first);
        const AttrSpec* spec = check_attr_name(specs, name, item.second.is_none(), owner_type, kind, mode, path);
        if (spec != nullptr) {
            check_attr_value(attr_input_from_py(item.second, *spec), *spec, path);
        }
    }
}

Mark mark_from_py(py::dict mark_dict, const Schema& schema, StrictMode mode, const PathStack& path,
                  std::vector<std::string>* keys) {
    Mark mark;
    mark.type = required_type(mark_dict, "mark", path);
    const MarkSpec* spec = require_mark_spec(schema, mark.type, path);
    if (mode != StrictMode::Off) {
        check_top_level_fields(mark_dict, mark.type, "mark", false, path);
    }

    const std::vector<AttrSpec>& specs = spec->attrs;
    py::object attrs = dict_get(mark_dict, "attrs");
    if (!attrs.is_none() || (mode != StrictMode::Off && dict_contains(mark_dict, "attrs"))) {
        py::dict attr_dict = expect_dict(attrs, "mark attrs", "attrs", path);
        if (mode != StrictMode::Off) {
            check_attrs_strict(attr_dict, specs, mark.type, "mark", mode, path);
        }
        mark.attrs = attrs_from_py(attr_dict, specs, keys);
    }
    // Outside the block above on purpose: a link mark with no attrs key at all
    // is a link with no destination just as much as one whose href is None.
    if (mode != StrictMode::Off) {
        check_required_attrs(mark.attrs, specs, mark.type, "mark", path);
    }

    return mark;
}

// Keep mark parsing outside fill_node_from_py's recursive frame: kMaxNodeDepth must
// remain safe on the smaller Windows worker stack even as strict checks grow.
void fill_marks_from_py(Node& node, py::object marks, const Schema& schema, StrictMode mode, PathStack& path,
                         NodeAttrKeys* keys) {
    if (marks.is_none()) {
        return;
    }

    py::list mark_list = expect_list(marks, "node marks", "marks", path);
    std::size_t mark_index = 0;
    for (py::handle mark_handle : mark_list) {
        path.push_back({"marks", mark_index});
        std::vector<std::string>* mark_keys = nullptr;
        if (keys != nullptr) {
            keys->marks.emplace_back();
            mark_keys = &keys->marks.back();
        }
        Mark mark = mark_from_py(expect_dict(mark_handle, "mark", "marks", path), schema, mode, path, mark_keys);
        if (mode != StrictMode::Off) {
            check_mark_set(node.marks, mark, schema, path);
        }
        node.marks.push_back(std::move(mark));
        path.pop_back();
        ++mark_index;
    }
}

// Keep node field/attr/mark parsing outside fill_node_from_py's recursive
// frame. kMaxNodeDepth must remain safe on small Windows worker stacks even as
// strict validation grows.
const NodeSpec* fill_node_fields_from_py(Document& document, std::size_t index, py::dict node_dict,
                                         std::string_view context, StrictMode mode, PathStack& path,
                                         NodeAttrKeys* keys) {
    Node node;
    node.type = required_type(node_dict, context, path);
    const Schema& schema = document.schema();
    const NodeSpec* spec = require_node_spec(schema, node.type, path);

    if (mode != StrictMode::Off) {
        check_top_level_fields(node_dict, node.type, "node", node_allows_marks(*spec), path);
        if (node.type == "text") {
            check_text_payload_py(node_dict, path);
        }
    }

    if (node.type == "text") {
        node.text = normalize_content_string(py_to_string(dict_get(node_dict, "text")));
    }

    const std::vector<AttrSpec>& specs = spec->attrs;
    py::object attrs = dict_get(node_dict, "attrs");
    if (!attrs.is_none() || (mode != StrictMode::Off && dict_contains(node_dict, "attrs"))) {
        py::dict attr_dict = expect_dict(attrs, "node attrs", "attrs", path);
        if (mode != StrictMode::Off) {
            check_attrs_strict(attr_dict, specs, node.type, "node", mode, path);
        }
        node.attrs = attrs_from_py(attr_dict, specs, keys != nullptr ? &keys->node : nullptr);
    }
    // Outside the block above: an image with no attrs key at all still has no src.
    if (mode != StrictMode::Off) {
        check_required_attrs(node.attrs, specs, node.type, "node", path);
        check_raw_carriers(node, schema, path);
    }

    py::object marks = dict_get(node_dict, "marks");
    if (mode != StrictMode::Off && marks.is_none() && dict_contains(node_dict, "marks")) {
        expect_list(marks, "node marks", "marks", path);
    }
    fill_marks_from_py(node, marks, schema, mode, path, keys);
    if (mode != StrictMode::Off && !spec->core) {
        check_node_marks(node, *spec, path);
    }

    document.node(index) = std::move(node);
    return spec;
}

const NodeSpec* fill_node_from_py(Document& document, std::size_t index, py::dict node_dict, std::string_view context,
                                  std::size_t depth, StrictMode mode, PathStack& path, InputAttrKeys* keys = nullptr) {
    check_node_depth(depth, path);

    if (keys != nullptr) {
        keys->resize(index + 1);
    }
    const NodeSpec* spec = fill_node_fields_from_py(document, index, node_dict, context, mode, path,
                                                   keys != nullptr ? &(*keys)[index] : nullptr);

    bool has_content = dict_contains(node_dict, "content");
    py::object content = dict_get(node_dict, "content");
    if (!has_content || (content.is_none() && mode == StrictMode::Off)) {
        if (mode != StrictMode::Off && !spec->core) {
            check_node_content(document, index, *spec, path);
        }
        return spec;
    }

    py::list content_list = expect_list(content, "node content", "content", path);
    if (mode != StrictMode::Off) {
        check_content_field(*spec, path);
    }
    std::size_t child_pos = 0;
    for (py::handle child_handle : content_list) {
        path.push_back({"content", child_pos});
        py::dict child_dict = expect_dict(child_handle, "content child", "content", path);
        std::size_t child_index = document.append_child(index, Node{});
        const NodeSpec* child = fill_node_from_py(document, child_index, child_dict, "node", depth + 1, mode, path,
                                                 keys);
        if (mode != StrictMode::Off) {
            check_child_content(document, *spec, *child, document.node(child_index),
                                content_list.size(), path);
        }
        path.pop_back();
        ++child_pos;
    }
    if (mode != StrictMode::Off && !spec->core) {
        check_node_content(document, index, *spec, path);
    }
    return spec;
}

}  // namespace

py::dict to_dict_py(const Document& document) {
    return node_to_py(document, 0);
}

Document from_dict_py(py::dict root, py::object link_schemes, py::object image_schemes, py::object link_relative,
                      py::object image_relative, py::object reject_node_types, py::object strict, py::object schema,
                      py::object base) {
    // Options are validated before the tree is walked:
    // a bad option value is a caller bug,
    // and should surface whatever the document happens to contain.
    UriPolicy policy = uri_policy_from_py(std::move(link_schemes), std::move(image_schemes), std::move(link_relative),
                                          std::move(image_relative));
    std::shared_ptr<const Schema> selected_schema = schema_from_py(schema);
    NodeTypePolicy node_policy = node_type_policy_from_py(std::move(reject_node_types), *selected_schema);
    StrictMode mode = strict_from_py(strict, "strict");
    const Document* inheritance_base = nullptr;
    if (!base.is_none()) {
        if (!py::isinstance<Document>(base)) {
            throw py::type_error("base must be a Document or None");
        }
        const Document& candidate = py::cast<const Document&>(base);
        if (candidate.schema().fingerprint() == selected_schema->fingerprint()) {
            inheritance_base = &candidate;
        }
    }

    PathStack path;
    path.reserve(32);

    std::string type = required_type(root, "root node", path);
    check_root_type(type, path);

    Document document(std::move(selected_schema));
    if (inheritance_base != nullptr) {
        InputAttrKeys present;
        fill_node_from_py(document, 0, root, "root node", 0, mode, path, &present);
        inherit_attrs_and_spelling(document, *inheritance_base, present);
    } else {
        fill_node_from_py(document, 0, root, "root node", 0, mode, path);
    }
    finalize_document(document, node_policy, policy);
    return document;
}

py::dict dump_py(const Document& document) {
    py::dict result;
    result["marktip"] = 1;
    result["schema"] = document.schema().fingerprint();
    const auto& spelling = document.spelling();
    py::dict options;
    options["html"] = spelling ? spelling->html : true;
    options["cjk_friendly"] = spelling ? spelling->cjk_friendly : false;
    result["options"] = std::move(options);
    result["doc"] = to_dict_py(document);
    std::optional<StoredSpelling> stored = dump_spelling(document);
    if (stored) {
        py::dict source;
        source["head"] = std::move(stored->head);
        py::list items;
        for (StoredPiece& piece : stored->items) {
            py::dict item;
            if (piece.text) {
                item["text"] = std::move(*piece.text);
            }
            item["sep"] = std::move(piece.sep);
            if (!piece.has_node) {
                item["node"] = false;
            }
            items.append(std::move(item));
        }
        source["items"] = std::move(items);
        result["source"] = std::move(source);
    }
    return result;
}

Document load_py(py::dict data, bool cjk_friendly, bool html, py::object schema) {
    py::object version = dict_get(data, "marktip");
    if (!py::isinstance<py::int_>(version) || py::cast<long long>(version) != 1) {
        throw py::value_error("unsupported marktip version");
    }
    PathStack path;
    py::dict content = expect_dict(dict_get(data, "doc"), "stored document", "doc", path);
    Document document = from_dict_py(content, py::none(), py::none(), py::str("allow"), py::str("allow"),
                                     py::none(), py::str("off"), std::move(schema), py::none());
    if (!dict_contains(data, "source")) {
        return document;
    }
    py::dict options = expect_dict(dict_get(data, "options"), "stored options", "options", path);
    if (py::cast<std::string>(dict_get(data, "schema")) != document.schema().fingerprint() ||
        py::cast<bool>(dict_get(options, "html")) != html ||
        py::cast<bool>(dict_get(options, "cjk_friendly")) != cjk_friendly) {
        return document;
    }
    py::dict source = expect_dict(dict_get(data, "source"), "stored source", "source", path);
    StoredSpelling stored;
    stored.head = py::cast<std::string>(dict_get(source, "head"));
    py::list items = expect_list(dict_get(source, "items"), "stored items", "items", path);
    stored.items.reserve(items.size());
    std::size_t blocks = 0;
    for (py::handle value : items) {
        py::dict item = expect_dict(value, "stored item", "items", path);
        StoredPiece piece;
        if (dict_contains(item, "text")) {
            piece.text = py::cast<std::string>(dict_get(item, "text"));
        }
        piece.sep = py::cast<std::string>(dict_get(item, "sep"));
        piece.has_node = !dict_contains(item, "node") || py::cast<bool>(dict_get(item, "node"));
        blocks += piece.has_node;
        stored.items.push_back(std::move(piece));
    }
    if (blocks == document.root().content.size()) {
        document.spelling() = restore_spelling(stored);
        document.spelling()->html = html;
        document.spelling()->cjk_friendly = cjk_friendly;
    }
    return document;
}

}  // namespace marktip
