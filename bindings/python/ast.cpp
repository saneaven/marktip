#include "bindings.h"

#include "document_input.h"
#include "document_output.h"
#include "input.h"
#include "output.h"

namespace py = pybind11;

namespace marktip {

py::dict to_dict_py(const Document& document) {
    return DocumentWriter<PythonOutput>::to_dict(document);
}

py::dict dump_py(const Document& document) {
    return DocumentWriter<PythonOutput>::dump(document);
}

Document from_dict_py(py::dict root, py::object link_schemes, py::object image_schemes, py::object link_relative,
                      py::object image_relative, py::object reject_node_types, py::object strict, py::object schema,
                      py::object base, bool cjk_friendly) {
    // Options are validated before the tree is walked.
    // A bad option value is a caller bug and should surface whatever the document contains.
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
        inheritance_base = &py::cast<const Document&>(base);
    }
    DictDocument document = DocumentReader<PythonInput>::from_dict(root, std::move(selected_schema), mode,
                                                                   inheritance_base);
    py::gil_scoped_release release;
    return std::move(document).finish(node_policy, policy, cjk_friendly);
}

Document load_py(py::dict data, py::object schema) {
    return DocumentReader<PythonInput>::load(data, schema_from_py(schema));
}

}  // namespace marktip
