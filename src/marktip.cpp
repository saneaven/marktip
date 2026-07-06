#include <pybind11/gil_safe_call_once.h>
#include <pybind11/pybind11.h>

#include <exception>
#include <string>

#include "ast.h"
#include "parser.h"
#include "serializer.h"

namespace py = pybind11;

#ifndef MARKTIP_VERSION
#define MARKTIP_VERSION "0.3.0"
#endif

PYBIND11_MODULE(_core, module) {
    module.doc() = "Fast MD4C-backed Markdown conversion with a C++ Document AST";
    module.attr("__version__") = MARKTIP_VERSION;

    // ValueError subclass carrying structured fields (.type, .path, .kind,
    // .detail) so callers can relay schema violations programmatically.
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> unknown_type_error_storage;
    unknown_type_error_storage.call_once_and_store_result([&]() -> py::object {
        py::object exc = py::exception<marktip::UnknownTypeError>(module, "UnknownTypeError", PyExc_ValueError);
        exc.attr("__module__") = "marktip._core";
        return exc;
    });

    py::register_exception_translator([](std::exception_ptr p) {
        if (!p) {
            return;
        }
        try {
            std::rethrow_exception(p);
        } catch (const marktip::UnknownTypeError& e) {
            const py::object& exc_type = unknown_type_error_storage.get_stored();
            py::object exc = exc_type(e.what());
            exc.attr("type") = e.type_name();
            exc.attr("path") = e.path();
            exc.attr("kind") = e.kind();
            exc.attr("detail") = std::string(e.what());
            PyErr_SetObject(exc_type.ptr(), exc.ptr());
        }
    });

    py::class_<marktip::Document>(module, "Document")
        .def("to_dict", &marktip::Document::to_dict, "Convert the document AST to a Tiptap-style JSON dict.")
        .def("to_markdown",
             [](const marktip::Document& document) {
                 return marktip::to_markdown(document);
             },
             "Serialize the document AST to canonical Markdown.");

    module.def("from_markdown", &marktip::from_markdown_py, py::arg("markdown"), py::arg("cjk_friendly") = false,
               py::arg("html") = true,
               "Parse Markdown into a Document. Set cjk_friendly=True to relax the emphasis rules around CJK text "
               "(non-standard extension; the default follows GFM/CommonMark exactly). Set html=False to parse raw "
               "HTML as literal text instead of htmlBlock/htmlInline nodes; <br> inside table cells still maps to "
               "hardBreak.");
    module.def("from_dict", &marktip::from_dict_py, py::arg("ast"), "Build a Document from a Tiptap-style JSON dict.");
}
