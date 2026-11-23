#include "ast.h"
#include "form.h"
#include "schema.h"

#include <algorithm>
#include <functional>

namespace marktip {
namespace {

bool same_node(const Document& left, std::size_t left_index, const Document& right, std::size_t right_index) {
    const Node& a = left.node(left_index);
    const Node& b = right.node(right_index);
    if (a.type != b.type || a.text != b.text || !equal_attrs(a.attrs, b.attrs) ||
        a.marks != b.marks || a.content.size() != b.content.size()) {
        return false;
    }
    for (std::size_t i = 0; i < a.content.size(); ++i) {
        if (!same_node(left, a.content[i], right, b.content[i])) {
            return false;
        }
    }
    return true;
}

void combine_hash(std::size_t& hash, std::size_t value) {
    hash ^= value + 0x9e3779b9u + (hash << 6) + (hash >> 2);
}

}  // namespace

bool same_document(const Document& left, const Document& right) {
    return left.schema().fingerprint() == right.schema().fingerprint() && same_node(left, 0, right, 0);
}

std::size_t document_hash(const Document& document) {
    std::size_t hash = std::hash<std::string> {}(document.schema().fingerprint());
    combine_hash(hash, block_hash(document, 0));
    return hash;
}

// Inheritance checks attrs and marks after lookup because input may omit attr keys or reorder marks.
std::size_t block_hash(const Document& document, std::size_t index) {
    const Node& node = document.node(index);
    std::size_t hash = std::hash<std::string> {}(node.type);
    combine_hash(hash, std::hash<std::string> {}(node.text));
    combine_hash(hash, node.marks.size());
    std::size_t marks = 0;
    for (const Mark& mark : node.marks) {
        marks += std::hash<std::string> {}(mark.type);
    }
    combine_hash(hash, marks);
    combine_hash(hash, node.content.size());
    for (std::size_t child : node.content) {
        combine_hash(hash, block_hash(document, child));
    }
    return hash;
}

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

const std::optional<Spelling>& Document::spelling() const {
    return spelling_;
}

std::optional<Spelling>& Document::spelling() {
    return spelling_;
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

void normalize_task_list(Document& document, std::size_t index) {
    Node& list = document.node(index);
    if (list.type != "bulletList") {
        return;
    }

    bool has_task = false;
    for (std::size_t child : list.content) {
        if (document.node(child).type == "taskItem") {
            has_task = true;
            break;
        }
    }
    if (!has_task) {
        return;
    }

    list.type = "taskList";
    for (std::size_t child : list.content) {
        Node& item = document.node(child);
        if (item.type == "listItem") {
            item.type = "taskItem";
            set_attr(item.attrs, "checked", AttrValue::boolean(false));
        }
    }
}

void order_marks(std::vector<Mark>& marks, const Schema& schema) {
    auto before = [&](const Mark& a, const Mark& b) {
        const MarkSpec& left = *schema.mark(a.type);
        const MarkSpec& right = *schema.mark(b.type);
        if (left.core != right.core) {
            return left.core;
        }
        if (left.core && schema.has_link_tag()) {
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
