#include "bindings.h"

#include <string>
#include <utility>

#include "parser.h"
#include "policy.h"
#include "schema.h"

namespace py = pybind11;

namespace marktip {

Document from_markdown_py(py::object markdown, bool cjk_friendly, bool html, py::object link_schemes,
                          py::object image_schemes, py::object link_relative, py::object image_relative,
                          py::object reject_node_types) {
    std::string input;
    if (py::isinstance<py::str>(markdown) || py::isinstance<py::bytes>(markdown)) {
        input = py::cast<std::string>(markdown);
    } else {
        throw py::type_error("from_markdown() expects str or bytes");
    }

    // Built while the GIL is still held: it reads Python objects.
    // The policy itself is plain std::string, so enforcing it below is safe without one.
    UriPolicy policy = uri_policy_from_py(std::move(link_schemes), std::move(image_schemes), std::move(link_relative),
                                          std::move(image_relative));
    NodeTypePolicy node_policy = node_type_policy_from_py(std::move(reject_node_types), *Schema::gfm());

    Document document;
    {
        py::gil_scoped_release release;
        // After the assignment, not before:
        // parse_to_document replaces the whole Document,
        // so anything checked earlier would be thrown away.
        document = parse_to_document(std::move(input), cjk_friendly, html);
        enforce_node_type_policy(document, node_policy);
        enforce_uri_policy(document, policy);
    }
    return document;
}

}  // namespace marktip
