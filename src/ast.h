#pragma once

#include <cstddef>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "errors.h"
#include "value.h"

namespace marktip {

class Schema;

// Deep documents are traversed recursively (to_dict, to_markdown); cap nesting
// at build time so those traversals cannot overflow the C stack.
inline constexpr std::size_t kMaxNodeDepth = 2048;

struct Node {
    std::string type;
    std::string text;
    AttrList attrs;
    std::vector<Mark> marks;
    std::vector<std::size_t> content;
};

void order_marks(std::vector<Mark>& marks, const Schema& schema);

class Document {
public:
    Document();
    explicit Document(std::size_t reserve_size);
    explicit Document(std::shared_ptr<const Schema> schema, std::size_t reserve_size = 32);

    const Node& root() const;
    Node& root();
    const Node& node(std::size_t index) const;
    Node& node(std::size_t index);
    const Schema& schema() const;

    std::size_t append_node(Node node);
    std::size_t append_child(std::size_t parent, Node node);

    void order_marks();

private:
    std::shared_ptr<const Schema> schema_;
    std::vector<Node> nodes_;
};

}  // namespace marktip
