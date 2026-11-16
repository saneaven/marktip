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
    bool inherit = false;
};

using ExcludeDeclaration = std::variant<std::monostate, std::string, std::vector<std::string>>;

struct MarkDeclaration {
    std::string name;
    std::optional<std::string> tag = std::nullopt;
    std::vector<AttrDeclaration> attrs = {};
    ExcludeDeclaration excludes = {};
};

struct NodeDeclaration {
    std::string name;
    std::string kind;
    std::optional<std::string> content = std::nullopt;
    std::optional<std::string> group = std::nullopt;
    std::optional<std::string> tag = std::nullopt;
    std::vector<AttrDeclaration> attrs = {};
    bool implicit = false;
    std::optional<std::string> fence = std::nullopt;
    std::optional<std::string> math = std::nullopt;
    std::optional<std::string> body = std::nullopt;
};

struct CoreAttrDeclaration {
    std::string type;
    std::vector<AttrDeclaration> attrs;
};

class SchemaBuilder {
public:
    static std::shared_ptr<Schema> build(std::vector<MarkDeclaration> marks, std::vector<NodeDeclaration> nodes,
                                         std::vector<CoreAttrDeclaration> core_attrs, bool block_image = false);

private:
    friend class Schema;
    static std::string fingerprint(const std::vector<MarkDeclaration>& marks,
                                    const std::vector<NodeDeclaration>& nodes,
                                    const std::vector<CoreAttrDeclaration>& core_attrs, bool block_image);
};

}  // namespace marktip
