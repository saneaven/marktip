#include "ast.h"
#include "form.h"
#include "schema.h"

#include <algorithm>

namespace marktip {

Document::Document() : Document(32) {}

Document::Document(std::size_t reserve_size) : Document(Schema::gfm(), reserve_size) {}

Document::Document(std::shared_ptr<const Schema> schema, std::size_t reserve_size) : schema_(std::move(schema)) {
    nodes_.reserve(reserve_size == 0 ? 1 : reserve_size);
    Node root_node;
    root_node.type = "doc";
    nodes_.push_back(std::move(root_node));
}

const Node& Document::root() const {
    return nodes_[0];
}

Node& Document::root() {
    return nodes_[0];
}

const Node& Document::node(std::size_t index) const {
    return nodes_[index];
}

Node& Document::node(std::size_t index) {
    return nodes_[index];
}

const Schema& Document::schema() const {
    return *schema_;
}

std::size_t Document::append_node(Node node) {
    nodes_.push_back(std::move(node));
    return nodes_.size() - 1;
}

std::size_t Document::append_child(std::size_t parent, Node node) {
    std::size_t index = append_node(std::move(node));
    nodes_[parent].content.push_back(index);
    return index;
}

void order_marks(std::vector<Mark>& marks, const Schema& schema) {
    auto before = [&](const Mark& a, const Mark& b) {
        const MarkSpec& left = *schema.mark(a.type);
        const MarkSpec& right = *schema.mark(b.type);
        if (left.core != right.core) {
            return left.core;
        }
        if (left.core && schema.has_core_attrs()) {
            // A tag link encloses the delimiter marks, so their original nesting order is not carried.
            return !uses_tag_form(a, left) && uses_tag_form(b, right);
        }
        return !left.core && left.order < right.order;
    };
    // The lift maintains this order, so its nodes need only a linear check here.
    if (!std::is_sorted(marks.begin(), marks.end(), before)) {
        std::stable_sort(marks.begin(), marks.end(), before);
    }
}

void Document::order_marks() {
    for (Node& node : nodes_) {
        marktip::order_marks(node.marks, *schema_);
    }
}

}  // namespace marktip
