#pragma once

#include <exception>
#include <string>
#include <utility>

namespace marktip {

// Every error marktip raises for bad input derives from MarktipError,
// so a caller can express "the document is malformed" as a single except clause.
//
// These types are thrown from parse_to_document() while the GIL is released,
// so they must never hold pybind11 objects — std::string members only.
class MarktipError : public std::exception {
public:
    MarktipError(std::string code, std::string message, std::string path = {})
        : code_(std::move(code)), message_(std::move(message)), path_(std::move(path)) {}

    const char* what() const noexcept override { return message_.c_str(); }

    const std::string& code() const noexcept { return code_; }
    const std::string& path() const noexcept { return path_; }

private:
    std::string code_;     // stable machine key, e.g. "wrong_type"
    std::string message_;
    std::string path_;     // "content[0].marks[1]"; empty = root / not applicable
};

// Raised by from_dict when a node or mark type is outside the closed schema.
class UnknownTypeError : public MarktipError {
public:
    UnknownTypeError(std::string kind, std::string type_name, std::string path)
        // path is passed by copy, not moved: argument evaluation order is unspecified,
        // and the message argument above reads it.
        : MarktipError("unknown_" + kind + "_type",
                       "unknown " + kind + " type '" + type_name + "' at " +
                           (path.empty() ? std::string("root") : path),
                       path),
          kind_(std::move(kind)),
          type_name_(std::move(type_name)) {}

    const std::string& kind() const noexcept { return kind_; }
    const std::string& type_name() const noexcept { return type_name_; }

private:
    std::string kind_;  // "node" | "mark"
    std::string type_name_;
};

// Raised when the input violates the node grammar itself: a missing 'type', a non-dict attrs,
// a non-list content, a root that is not a doc.
class InvalidNodeError : public MarktipError {
public:
    InvalidNodeError(std::string code, std::string field, std::string message, std::string path)
        : MarktipError(std::move(code), std::move(message), std::move(path)), field_(std::move(field)) {}

    const std::string& field() const noexcept { return field_; }

private:
    std::string field_;  // "type" | "attrs" | "marks" | "content"
};

// Raised by from_markdown when the markdown itself cannot be parsed.
class ParseError : public MarktipError {
public:
    ParseError(std::string code, std::string message) : MarktipError(std::move(code), std::move(message)) {}
};

}  // namespace marktip
