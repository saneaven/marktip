#include <pybind11/gil_safe_call_once.h>
#include <pybind11/pybind11.h>

#include <exception>
#include <string>

#include "ast.h"
#include "bindings.h"
#include "input.h"
#include "schema_input.h"
#include "serializer.h"

namespace py = pybind11;

#ifndef MARKTIP_VERSION
#define MARKTIP_VERSION "0.8.3"
#endif

namespace {

struct IntList {};
struct StrMap {};

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

    py::class_<IntList>(module, "IntList");
    py::class_<StrMap>(module, "StrMap");

    py::class_<marktip::Schema, std::shared_ptr<marktip::Schema>>(module, "Schema")
        .def(py::init([](py::object declaration) {
            return marktip::SchemaDeclarationReader<marktip::PythonInput>::read(declaration);
        }), py::arg("declaration"));

    py::class_<marktip::Document>(module, "Document")
        .def("__eq__", &marktip::same_document, py::is_operator())
        .def("__hash__", &marktip::document_hash)
        .def("to_dict", &marktip::to_dict_py, "Convert the document AST to a Tiptap-style JSON dict.")
        .def("dump", &marktip::dump_py, "Return JSON-serializable content, spelling and schema.")
        .def("to_markdown",
             [](const marktip::Document& document, bool canonical) {
                 return marktip::to_markdown(document, canonical);
             },
             py::arg("canonical") = false,
             "Write Markdown with remembered source spelling. Pass canonical=True to write the whole AST canonically.");

    // The URI policy is keyword-only and documented once here;
    // the README carries the prose.
    // It behaves identically on both entry points, because both are write boundaries:
    // an editor submits an AST, agents and imports submit Markdown strings,
    // and both end up stored.
    const std::string uri_policy_doc =
        " Pass link_schemes/image_schemes an iterable of scheme names to restrict link href / image src to that set."
        " None (the default) allows every scheme, () allows none, and comparison is case-insensitive."
        " Pass link_relative/image_relative one of 'allow' (the default), 'path_only' or 'reject'."
        " Those govern references carrying no scheme; 'path_only' rejects protocol-relative '//host/x'."
        " Violations raise InvalidNodeError with .code 'disallowed_scheme' or 'disallowed_relative_url'."
        " An ASCII control character that reaches href/src is always rejected with .code 'invalid_uri_char';"
        " Markdown U+0000 is normalized to U+FFFD before parsing.";
    const std::string node_policy_doc =
        " Pass reject_node_types an iterable of known node type names to refuse those nodes."
        " None (the default) refuses none."
        " A match raises InvalidNodeError with .code 'disallowed_node_type',"
        " .field 'type' and .path locating the node.";

    // Held in locals rather than passed as temporaries:
    // pybind11 takes the doc as a bare const char* and only copies it while def() runs.
    const std::string from_markdown_doc =
        "Parse Markdown into a Document."
        " Pass schema=Schema(...) to use declared marks and nodes, fence and math carriers,"
        " and attrs added to core types through core_attrs;"
        " None (the default) uses the built-in GFM schema."
        " Declared tag attrs, mark sets and content expressions are validated while reading."
        " Malformed declared tags raise InvalidNodeError with .code 'invalid_tag' and a document path."
        " Set cjk_friendly=True to use CJK-friendly emphasis and strikethrough rules (non-standard extension;"
        " the default follows GFM/CommonMark exactly)."
        " Set html=False to parse raw HTML as literal text instead of htmlBlock/htmlInline nodes;"
        " <br> inside table cells still maps to hardBreak."
        " Declared tags are recognized even when html=False."
        " Set partial=True to read open declared tags as closed where their parent ends;"
        " unmatched closing tags, invalid attrs and content-model violations still raise errors."
        " Set keep_source=False to skip source spelling;"
        " to_markdown() then writes canonical Markdown and dump() omits source."
        " These keyword-only options default to partial=False and keep_source=True and are independent." +
        uri_policy_doc + node_policy_doc;
    // strict has no from_markdown counterpart on purpose: the parser only ever emits
    // declared fields, valid content relationships and attrs it understands.
    const std::string from_dict_doc =
        "Build a Document from a Tiptap-style JSON dict."
        " If the document's Markdown will be read with CJK-friendly emphasis and strikethrough rules,"
        " set cjk_friendly=True."
        " Pass base=Document to reuse spelling of equal blocks from that document."
        " Matched blocks inherit attrs whose keys are absent; a key set to None is cleared."
        " A base with a different schema declaration lends nothing."
        " Pass schema=Schema(...) to use declared marks and nodes, fence and math carriers,"
        " and attrs added to core types through core_attrs;"
        " None (the default) uses the built-in GFM schema." +
        uri_policy_doc + node_policy_doc +
        " strict names what the conversion may not lose, rather than converting around everything:"
        " 'off' (the default) checks no attrs at all,"
        " 'content' keeps content and structure and drops presentation only,"
        " 'exact' keeps every attr the JSON carries, except declared defaults that mean unset."
        " With the default schema, the two levels differ over presentation attrs."
        " These are link target/rel/class, image width/height, orderedList type and tableCell colwidth."
        " 'content' type-checks them and drops them; 'exact' refuses them."
        " Violations raise InvalidNodeError with .field set to the attr name."
        " Its .code is one of 'unknown_attr' (a name outside both dialects),"
        " 'invalid_attr_value' (wrong type or out of range),"
        " 'unrepresentable' (well-formed, but GFM cannot carry it, e.g. colspan=2)"
        " or 'missing_attr' (a link with no href, an image with no src, which would serialize as '[a]()')."
        " Strict rejects excluded mark combinations and duplicate marks of the same type and attrs."
        " These raise InvalidNodeError with .field 'marks' and .code 'invalid_mark_set'."
        " In strict modes, for blocks without remembered spelling,"
        " emphasis that the writer's one spelling cannot carry raises InvalidNodeError with .code 'unrepresentable'."
        " Some of these trees have another spelling that marktip does not search for."
        " Declared inline atoms and containers accept a marks field at every strict level."
        " Strict also refuses a code mark on a declared inline atom or container with .code 'invalid_mark_set'."
        " With strict='off', serialization writes the node outside code spans and omits its code mark."
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
               py::arg("schema") = py::none(), py::arg("partial") = false, py::arg("keep_source") = true,
               from_markdown_doc.c_str());
    module.def("from_dict", &marktip::from_dict_py, py::arg("ast"), py::kw_only(),
               py::arg("link_schemes") = py::none(), py::arg("image_schemes") = py::none(),
               py::arg("link_relative") = "allow",
               py::arg("image_relative") = "allow", py::arg("reject_node_types") = py::none(),
               py::arg("strict") = "off", py::arg("schema") = py::none(), py::arg("base") = py::none(),
               py::arg("cjk_friendly") = false, from_dict_doc.c_str());
    module.def("load", &marktip::load_py, py::arg("data"), py::kw_only(), py::arg("schema") = py::none(),
               "Load a Document saved by dump()."
               " Restore spelling when the schema declaration matches."
               " Otherwise only content is loaded."
               " Stored spelling is not reparsed or checked against content."
               " An unknown marktip version raises ValueError.");
}
