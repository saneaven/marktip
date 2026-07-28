#include <pybind11/gil_safe_call_once.h>
#include <pybind11/pybind11.h>

#include <exception>
#include <string>

#include "ast.h"
#include "parser.h"
#include "serializer.h"

namespace py = pybind11;

#ifndef MARKTIP_VERSION
#define MARKTIP_VERSION "0.6.0"
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

    py::class_<marktip::Document>(module, "Document")
        .def("to_dict", &marktip::Document::to_dict, "Convert the document AST to a Tiptap-style JSON dict.")
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
        " An ASCII control character in href/src is always rejected with .code 'invalid_uri_char',"
        " options or not.";

    // Held in locals rather than passed as temporaries:
    // pybind11 takes the doc as a bare const char* and only copies it while def() runs.
    const std::string from_markdown_doc =
        "Parse Markdown into a Document."
        " Set cjk_friendly=True to relax the emphasis rules around CJK text"
        " (non-standard extension; the default follows GFM/CommonMark exactly)."
        " Set html=False to parse raw HTML as literal text instead of htmlBlock/htmlInline nodes;"
        " <br> inside table cells still maps to hardBreak." +
        uri_policy_doc;
    // strict has no from_markdown counterpart on purpose:
    // the parser only ever emits attrs it understands, with values in range.
    const std::string from_dict_doc =
        "Build a Document from a Tiptap-style JSON dict." + uri_policy_doc +
        " Set strict=True to refuse any attr that would be dropped or altered on the way to markdown"
        " instead of converting around it."
        " Violations raise InvalidNodeError with .code 'unknown_attr' (no markdown form for that type),"
        " 'invalid_attr_value' (wrong type or out of range) or 'unrepresentable'"
        " (well-formed, but GFM cannot carry it, e.g. colspan=2), and .field set to the attr name."
        " table 'colCount' and a non-header row's 'align' are accepted and ignored,"
        " because from_markdown emits both."
        " None is accepted on the attrs Tiptap declares `default: null`"
        " (codeBlock language/info, image src/alt/title, link href/title):"
        " it means the attr is unset, and from_dict drops the key rather than coercing it to ''.";

    module.def("from_markdown", &marktip::from_markdown_py, py::arg("markdown"), py::arg("cjk_friendly") = false,
               py::arg("html") = true, py::kw_only(), py::arg("link_schemes") = py::none(),
               py::arg("image_schemes") = py::none(), py::arg("link_relative") = "allow",
               py::arg("image_relative") = "allow", from_markdown_doc.c_str());
    module.def("from_dict", &marktip::from_dict_py, py::arg("ast"), py::kw_only(),
               py::arg("link_schemes") = py::none(), py::arg("image_schemes") = py::none(),
               py::arg("link_relative") = "allow", py::arg("image_relative") = "allow", py::arg("strict") = false,
               from_dict_doc.c_str());
}
