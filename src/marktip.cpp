#include <pybind11/pybind11.h>

#include "parser.h"
#include "serializer.h"

namespace py = pybind11;

#ifndef MARKTIP_VERSION
#define MARKTIP_VERSION "0.2.0"
#endif

PYBIND11_MODULE(_core, module) {
    module.doc() = "Fast MD4C-backed Markdown conversion with a C++ Document AST";
    module.attr("__version__") = MARKTIP_VERSION;

    py::class_<marktip::Document>(module, "Document")
        .def("to_dict", &marktip::Document::to_dict, "Convert the document AST to a Tiptap-style JSON dict.")
        .def("to_markdown",
             [](const marktip::Document& document) {
                 return marktip::to_markdown(document);
             },
             "Serialize the document AST to canonical Markdown.");

    module.def("from_markdown", &marktip::from_markdown_py, py::arg("markdown"), py::arg("cjk_friendly") = false,
               "Parse Markdown into a Document. Set cjk_friendly=True to relax the emphasis rules around CJK text "
               "(non-standard extension; the default follows GFM/CommonMark exactly).");
    module.def("from_dict", &marktip::from_dict_py, py::arg("ast"), "Build a Document from a Tiptap-style JSON dict.");
}
