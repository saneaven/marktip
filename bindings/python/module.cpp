#include <pybind11/gil_safe_call_once.h>
#include <pybind11/pybind11.h>

#include <exception>
#include <string>

#include "ast.h"
#include "bindings.h"
#include "schema_builder.h"
#include "serializer.h"

namespace py = pybind11;

#ifndef MARKTIP_VERSION
#define MARKTIP_VERSION "0.7.3"
#endif

namespace {

// Builds the Python exception instance and fills the fields every MarktipError carries.
// The caller attaches any subclass-specific fields, then raises it.
py::object make_marktip_error(const py::object& exc_type, const marktip::MarktipError& e) {
    py::object exc = exc_type(e.what());
    exc.attr("code") = e.code();
    exc.attr("path") = e.path();
    exc.attr("detail") = std::string(e.what());
    return exc;
}

std::string declaration_string(py::handle value, const char* field) {
    if (!py::isinstance<py::str>(value)) {
        throw py::type_error(std::string(field) + " must be a str");
    }
    return py::cast<std::string>(value);
}

std::optional<std::string> declaration_optional_string(py::handle value, const char* field) {
    if (value.is_none()) {
        return std::nullopt;
    }
    return declaration_string(value, field);
}

marktip::AttrValue declaration_value(py::handle value) {
    if (py::isinstance<py::bool_>(value)) {
        return marktip::AttrValue::boolean(py::cast<bool>(value));
    }
    if (py::isinstance<py::int_>(value)) {
        int overflow = 0;
        long long number = PyLong_AsLongLongAndOverflow(value.ptr(), &overflow);
        if (overflow != 0) {
            PyErr_Clear();
            throw py::value_error("declaration integer must fit in long long");
        }
        return marktip::AttrValue::integer(number);
    }
    if (py::isinstance<py::str>(value)) {
        return marktip::AttrValue::string(declaration_string(value, "declaration value"));
    }
    throw py::value_error("declaration values must be str, int or bool");
}

marktip::AttrRule declaration_rule(py::handle value) {
    if (value.ptr() == reinterpret_cast<PyObject*>(&PyUnicode_Type)) {
        return marktip::AttrRule::Str;
    }
    if (value.ptr() == reinterpret_cast<PyObject*>(&PyLong_Type)) {
        return marktip::AttrRule::Int;
    }
    if (value.ptr() == reinterpret_cast<PyObject*>(&PyBool_Type)) {
        return marktip::AttrRule::Bool;
    }
    throw py::type_error("Attr.type must be str, int or bool");
}

std::vector<std::string> declaration_names(py::handle value, const char* field) {
    std::vector<std::string> names;
    for (py::handle item : py::reinterpret_borrow<py::object>(value)) {
        names.push_back(declaration_string(item, field));
    }
    return names;
}

marktip::AttrDeclaration attr_declaration_from_py(const std::string& name, py::handle value) {
    marktip::AttrDeclaration result;
    result.name = name;
    result.rule = declaration_rule(value.attr("type"));
    py::object required = value.attr("required");
    if (!py::isinstance<py::bool_>(required)) {
        throw py::type_error("required must be a bool");
    }
    result.required = py::cast<bool>(required);
    py::object choices = value.attr("choices");
    if (!choices.is_none()) {
        if (!py::isinstance<py::tuple>(choices) && !py::isinstance<py::list>(choices)) {
            throw py::type_error("choices must be a tuple or list");
        }
        result.choices.emplace();
        for (py::handle choice : choices) {
            result.choices->push_back(declaration_value(choice));
        }
    }
    py::object fallback = value.attr("default");
    if (!fallback.is_none()) {
        result.fallback = declaration_value(fallback);
    }
    result.uri = declaration_optional_string(value.attr("uri"), "uri");
    return result;
}

std::vector<marktip::AttrDeclaration> attr_declarations_from_py(py::handle values) {
    if (!py::isinstance<py::dict>(values)) {
        throw py::type_error("attrs must be a dict");
    }
    std::vector<marktip::AttrDeclaration> attrs;
    for (auto attr : py::reinterpret_borrow<py::dict>(values)) {
        std::string name = declaration_string(attr.first, "attr name");
        attrs.push_back(attr_declaration_from_py(name, attr.second));
    }
    return attrs;
}

std::vector<marktip::MarkDeclaration> mark_declarations_from_py(py::handle values) {
    std::vector<marktip::MarkDeclaration> result;
    for (py::handle value : py::reinterpret_borrow<py::object>(values)) {
        marktip::MarkDeclaration mark;
        mark.name = declaration_string(value.attr("name"), "mark name");
        mark.tag = declaration_optional_string(value.attr("tag"), "tag");
        mark.attrs = attr_declarations_from_py(value.attr("attrs"));
        py::object excludes = value.attr("excludes");
        if (py::isinstance<py::str>(excludes)) {
            mark.excludes = declaration_string(excludes, "excludes");
        } else if (!excludes.is_none()) {
            if (!py::isinstance<py::tuple>(excludes)) {
                throw py::type_error("excludes must be None, '_' or a tuple of mark names");
            }
            mark.excludes = declaration_names(excludes, "excludes entries");
        }
        result.push_back(std::move(mark));
    }
    return result;
}

std::vector<marktip::NodeDeclaration> node_declarations_from_py(py::handle values) {
    std::vector<marktip::NodeDeclaration> result;
    for (py::handle value : py::reinterpret_borrow<py::object>(values)) {
        marktip::NodeDeclaration node;
        node.name = declaration_string(value.attr("name"), "node name");
        node.kind = declaration_string(value.attr("kind"), "kind");
        node.content = declaration_optional_string(value.attr("content"), "content");
        node.group = declaration_optional_string(value.attr("group"), "group");
        node.tag = declaration_optional_string(value.attr("tag"), "tag");
        node.attrs = attr_declarations_from_py(value.attr("attrs"));
        py::object implicit = value.attr("implicit");
        if (!py::isinstance<py::bool_>(implicit)) {
            throw py::type_error("implicit must be a bool");
        }
        node.implicit = py::cast<bool>(implicit);
        result.push_back(std::move(node));
    }
    return result;
}

}  // namespace

PYBIND11_MODULE(_core, module) {
    module.doc() = "Fast MD4C-backed Markdown conversion with a C++ Document AST";
    module.attr("__version__") = MARKTIP_VERSION;

    // Every marktip error derives from MarktipError,
    // so a caller can express "the input is malformed" as a single except clause.
    // Each instance carries structured fields (.code, .path, .detail, plus subclass-specific ones),
    // so violations can be relayed programmatically.
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> marktip_error_storage;
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> unknown_type_error_storage;
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> invalid_node_error_storage;
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> parse_error_storage;

    marktip_error_storage.call_once_and_store_result([&]() -> py::object {
        py::object exc = py::exception<marktip::MarktipError>(module, "MarktipError", PyExc_Exception);
        exc.attr("__module__") = "marktip._core";
        return exc;
    });
    const py::object& marktip_error = marktip_error_storage.get_stored();

    unknown_type_error_storage.call_once_and_store_result([&]() -> py::object {
        py::object exc = py::exception<marktip::UnknownTypeError>(module, "UnknownTypeError", marktip_error);
        exc.attr("__module__") = "marktip._core";
        return exc;
    });
    invalid_node_error_storage.call_once_and_store_result([&]() -> py::object {
        py::object exc = py::exception<marktip::InvalidNodeError>(module, "InvalidNodeError", marktip_error);
        exc.attr("__module__") = "marktip._core";
        return exc;
    });
    parse_error_storage.call_once_and_store_result([&]() -> py::object {
        py::object exc = py::exception<marktip::ParseError>(module, "ParseError", marktip_error);
        exc.attr("__module__") = "marktip._core";
        return exc;
    });

    // register_exception_translator takes a plain function pointer,
    // so this lambda must stay non-capturing; the storages above are static.
    py::register_exception_translator([](std::exception_ptr p) {
        if (!p) {
            return;
        }
        // Most-derived first: a base-class catch would shadow the subclasses.
        try {
            std::rethrow_exception(p);
        } catch (const marktip::UnknownTypeError& e) {
            const py::object& exc_type = unknown_type_error_storage.get_stored();
            py::object exc = make_marktip_error(exc_type, e);
            exc.attr("type") = e.type_name();
            exc.attr("kind") = e.kind();
            PyErr_SetObject(exc_type.ptr(), exc.ptr());
        } catch (const marktip::InvalidNodeError& e) {
            const py::object& exc_type = invalid_node_error_storage.get_stored();
            py::object exc = make_marktip_error(exc_type, e);
            exc.attr("field") = e.field();
            PyErr_SetObject(exc_type.ptr(), exc.ptr());
        } catch (const marktip::ParseError& e) {
            const py::object& exc_type = parse_error_storage.get_stored();
            PyErr_SetObject(exc_type.ptr(), make_marktip_error(exc_type, e).ptr());
        } catch (const marktip::MarktipError& e) {
            const py::object& exc_type = marktip_error_storage.get_stored();
            PyErr_SetObject(exc_type.ptr(), make_marktip_error(exc_type, e).ptr());
        }
    });

    py::class_<marktip::Schema, std::shared_ptr<marktip::Schema>>(module, "Schema")
        .def(py::init([](py::object marks, py::object nodes) {
            return marktip::SchemaBuilder::build(mark_declarations_from_py(marks), node_declarations_from_py(nodes));
        }), py::kw_only(), py::arg("marks") = py::tuple(), py::arg("nodes") = py::tuple());

    py::class_<marktip::Document>(module, "Document")
        .def("to_dict", &marktip::to_dict_py, "Convert the document AST to a Tiptap-style JSON dict.")
        .def("to_markdown",
             [](const marktip::Document& document) {
                 return marktip::to_markdown(document);
             },
             "Serialize the document AST to canonical Markdown.");

    // The URI policy is keyword-only and documented once here;
    // the README carries the prose.
    // It behaves identically on both entry points, because both are write boundaries:
    // an editor submits an AST, agents and imports submit Markdown strings,
    // and both end up stored.
    const std::string uri_policy_doc =
        " Pass link_schemes/image_schemes an iterable of scheme names"
        " to restrict link href / image src to that set."
        " None (the default) allows every scheme, () allows none, and comparison is case-insensitive."
        " Pass link_relative/image_relative one of 'allow' (the default), 'path_only' or 'reject'."
        " Those govern references carrying no scheme; 'path_only' rejects protocol-relative '//host/x'."
        " Violations raise InvalidNodeError with .code 'disallowed_scheme' or 'disallowed_relative_url'."
        " An ASCII control character that reaches href/src is always rejected with .code 'invalid_uri_char';"
        " Markdown U+0000 is normalized to U+FFFD before parsing.";
    const std::string node_policy_doc =
        " Pass reject_node_types an iterable of known node type names to refuse those nodes."
        " None (the default) refuses none."
        " A match raises InvalidNodeError with .code 'disallowed_node_type', .field 'type'"
        " and .path locating the node.";

    // Held in locals rather than passed as temporaries:
    // pybind11 takes the doc as a bare const char* and only copies it while def() runs.
    const std::string from_markdown_doc =
        "Parse Markdown into a Document."
        " Pass schema=Schema(...) to recognize declared tag marks and inline nodes;"
        " None (the default) uses the built-in GFM schema."
        " Declared tag attrs, mark sets and content expressions are validated while reading."
        " Malformed declared tags raise InvalidNodeError with .code 'invalid_tag' and a document path."
        " Set cjk_friendly=True to use CJK-friendly emphasis and strikethrough rules"
        " (non-standard extension; the default follows GFM/CommonMark exactly)."
        " Set html=False to parse raw HTML as literal text instead of htmlBlock/htmlInline nodes;"
        " <br> inside table cells still maps to hardBreak."
        " Declared tags are recognized even when html=False." +
        uri_policy_doc + node_policy_doc;
    // strict has no from_markdown counterpart on purpose: the parser only ever emits
    // declared fields, valid content relationships and attrs it understands.
    const std::string from_dict_doc =
        "Build a Document from a Tiptap-style JSON dict."
        " Pass schema=Schema(...) to include declared marks and inline nodes;"
        " None (the default) uses the built-in GFM schema." +
        uri_policy_doc + node_policy_doc +
        " strict names what the conversion may not lose, rather than converting around everything:"
        " 'off' (the default) checks no attrs at all,"
        " 'content' keeps content and structure and drops presentation only,"
        " 'exact' keeps every attr the JSON carries."
        " The two differ over the attrs an editor stamps on that markdown has no form for"
        " (link target/rel/class, image width/height, orderedList type, tableCell colwidth):"
        " 'content' type-checks them and drops them, 'exact' refuses them."
        " Violations raise InvalidNodeError with .field set to the attr name and .code one of"
        " 'unknown_attr' (a name outside both dialects), 'invalid_attr_value' (wrong type or out of range),"
        " 'unrepresentable' (well-formed, but GFM cannot carry it, e.g. colspan=2)"
        " or 'missing_attr' (a link with no href, an image with no src, which would serialize as '[a]()')."
        " Strict rejects excluded mark combinations and duplicate marks of the same type and attrs."
        " These raise InvalidNodeError with .field 'marks' and .code 'invalid_mark_set'."
        " A declared inline atom also refuses the code mark with .code 'invalid_mark_set'."
        " A declared inline container refuses a marks field with .code 'unknown_field'."
        " Strict rejects htmlInline containing a declared tag and htmlBlock beginning with one."
        " These use .code 'unrepresentable', .field 'html' and .path locating the raw HTML node."
        " Strict also closes node/mark top-level fields and each node's content model;"
        " violations use .code 'unknown_field' or 'invalid_content'."
        " table 'colCount' and a non-header row's 'align' are accepted at every level,"
        " because from_markdown emits both and the structure carries them anyway."
        " None means the attr was never set wherever Tiptap declares `default: null`,"
        " and from_dict drops the key rather than coercing it.";

    module.def("from_markdown", &marktip::from_markdown_py, py::arg("markdown"), py::arg("cjk_friendly") = false,
               py::arg("html") = true, py::kw_only(), py::arg("link_schemes") = py::none(),
               py::arg("image_schemes") = py::none(), py::arg("link_relative") = "allow",
               py::arg("image_relative") = "allow", py::arg("reject_node_types") = py::none(),
               py::arg("schema") = py::none(),
               from_markdown_doc.c_str());
    module.def("from_dict", &marktip::from_dict_py, py::arg("ast"), py::kw_only(),
               py::arg("link_schemes") = py::none(), py::arg("image_schemes") = py::none(),
               py::arg("link_relative") = "allow",
               py::arg("image_relative") = "allow", py::arg("reject_node_types") = py::none(),
               py::arg("strict") = "off", py::arg("schema") = py::none(), from_dict_doc.c_str());
}
