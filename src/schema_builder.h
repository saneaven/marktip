#pragma once

#include <memory>
#include <optional>
#include <string>
#include <variant>
#include <vector>

#include "schema.h"

namespace marktip {

struct AttrDeclaration {
    std::string name;
    AttrRule rule;
    bool required = false;
    std::optional<std::vector<AttrValue>> choices = std::nullopt;
    std::optional<AttrValue> fallback = std::nullopt;
    std::optional<std::string> uri = std::nullopt;
};

using ExcludeDeclaration = std::variant<std::monostate, std::string, std::vector<std::string>>;

struct MarkDeclaration {
    std::string name;
    std::optional<std::string> tag = std::nullopt;
    std::vector<AttrDeclaration> attrs = {};
    ExcludeDeclaration excludes = {};
};

class SchemaBuilder {
public:
    static std::shared_ptr<Schema> build(std::vector<MarkDeclaration> marks);
};

}  // namespace marktip
