#pragma once

#include <cstddef>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "errors.h"
#include "spelling.h"
#include "value.h"

namespace marktip {

class Schema;

// Deep document traversals recurse; cap nesting for the smallest binding stack.
// In wasm, that includes the JS engine's call stack.
inline constexpr std::size_t kMaxNodeDepth = 512;

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
    std::size_t node_count() const;
    const Schema& schema() const;
    const std::optional<Spelling>& spelling() const;
    std::optional<Spelling>& spelling();

    std::size_t append_node(Node node);
    std::size_t append_child(std::size_t parent, Node node);

private:
    std::shared_ptr<const Schema> schema_;
    std::vector<Node> nodes_;
    std::optional<Spelling> spelling_;
};

bool same_document(const Document& left, const Document& right);
std::size_t document_hash(const Document& document);
std::size_t block_hash(const Document& document, std::size_t index);
std::string plain_text(const Document& document, const Node& node);
bool is_table_cell(std::string_view type);
std::size_t table_columns(const Document& document, const Node& table);

void normalize_task_list(Document& document, std::size_t index);

}  // namespace marktip
