#include "bindings.h"

namespace py = pybind11;

namespace marktip {

// Spelled like the relative policy below rather than as a bool,
// because the interesting question has three answers and only one of them is "do not check".
StrictMode strict_from_py(py::handle value, const char* arg_name) {
    if (!py::isinstance<py::str>(value)) {
        throw py::type_error(std::string(arg_name) + " must be a str");
    }
    return strict_mode_from_string(py::cast<std::string>(value), arg_name);
}

namespace {

RelativePolicy relative_from_py(py::handle value, const char* arg_name) {
    if (!py::isinstance<py::str>(value)) {
        throw py::type_error(std::string(arg_name) + " must be a str");
    }
    return relative_policy_from_string(py::cast<std::string>(value), arg_name);
}

void schemes_from_py(py::handle value, const char* arg_name, UriRule& rule) {
    if (value.is_none()) {
        return;  // no restriction: every scheme is allowed, which is the default
    }
    if (py::isinstance<py::str>(value) || py::isinstance<py::bytes>(value)) {
        // Iterating a bare "https" would silently build the set {h, t, p, s}.
        throw py::type_error(std::string(arg_name) + " must be an iterable of str, not a single str");
    }

    // An empty iterable is meaningful and distinct from None:
    // it allows no scheme at all, leaving only whatever the relative policy permits.
    rule.restrict_schemes = true;
    for (py::handle item : py::reinterpret_borrow<py::object>(value)) {
        if (!py::isinstance<py::str>(item)) {
            throw py::type_error(std::string(arg_name) + " entries must be str");
        }
        add_uri_scheme(rule, py::cast<std::string>(item), arg_name);
    }
}

void rejected_node_types_from_py(py::handle value, const char* arg_name, const Schema& schema,
                                 NodeTypePolicy& policy) {
    if (value.is_none()) {
        return;
    }
    if (py::isinstance<py::str>(value) || py::isinstance<py::bytes>(value)) {
        throw py::type_error(std::string(arg_name) + " must be an iterable of str, not a single str");
    }

    for (py::handle item : py::reinterpret_borrow<py::object>(value)) {
        if (!py::isinstance<py::str>(item)) {
            throw py::type_error(std::string(arg_name) + " entries must be str");
        }
        add_rejected_node_type(policy, py::cast<std::string>(item), schema, arg_name);
    }
}

}  // namespace

UriPolicy uri_policy_from_py(py::object link_schemes, py::object image_schemes, py::object link_relative,
                             py::object image_relative) {
    UriPolicy policy;
    schemes_from_py(link_schemes, "link_schemes", policy.link);
    schemes_from_py(image_schemes, "image_schemes", policy.image);
    policy.link.relative = relative_from_py(link_relative, "link_relative");
    policy.image.relative = relative_from_py(image_relative, "image_relative");
    return policy;
}

NodeTypePolicy node_type_policy_from_py(py::object reject_node_types, const Schema& schema) {
    NodeTypePolicy policy;
    rejected_node_types_from_py(reject_node_types, "reject_node_types", schema, policy);
    return policy;
}

}  // namespace marktip
