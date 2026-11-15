#include "inherit.h"

#include <algorithm>
#include <functional>
#include <optional>
#include <unordered_map>
#include <utility>

#include "schema.h"

namespace marktip {
namespace {

bool has_key(const std::vector<std::string>& keys, const std::string& name) {
    return std::find(keys.begin(), keys.end(), name) != keys.end();
}

bool same_attrs(const AttrList& current, const AttrList& original, const std::vector<AttrSpec>& specs,
                const std::vector<std::string>& present) {
    for (const AttrSpec& spec : specs) {
        if (!attr_is_carried(spec) || !has_key(present, spec.name)) {
            continue;
        }
        const AttrValue* left = find_attr(current, spec.name);
        const AttrValue* right = find_attr(original, spec.name);
        if ((left == nullptr) != (right == nullptr) || (left != nullptr && !(*left == *right))) {
            return false;
        }
    }
    return true;
}

void inherit_attrs(AttrList& current, const AttrList& original, const std::vector<std::string>& present) {
    for (const auto& attr : original) {
        if (!has_key(present, attr.first)) {
            set_attr(current, attr.first, attr.second);
        }
    }
}

void combine_hash(std::size_t& hash, std::size_t value) {
    hash ^= value + 0x9e3779b9u + (hash << 6) + (hash >> 2);
}

// Attrs are checked after lookup because an editor may omit any of their keys.
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

class BlockComparison {
public:
    BlockComparison(Document& document, const Document& base, const InputAttrKeys& present)
        : document_(document), base_(base), present_(present) {}

    bool same(std::size_t current_index, std::size_t original_index) const {
        const Node& current = document_.node(current_index);
        const Node& original = base_.node(original_index);
        if (current.type != original.type || current.text != original.text ||
            current.content.size() != original.content.size()) {
            return false;
        }
        const NodeSpec& spec = *document_.schema().node(current.type);
        if (!same_attrs(current.attrs, original.attrs, spec.attrs, present_[current_index].node) ||
            !mark_pairs(current_index, original_index)) {
            return false;
        }
        for (std::size_t i = 0; i < current.content.size(); ++i) {
            if (!same(current.content[i], original.content[i])) {
                return false;
            }
        }
        return true;
    }

    void fill(std::size_t current_index, std::size_t original_index) {
        Node& current = document_.node(current_index);
        const Node& original = base_.node(original_index);
        inherit_attrs(current.attrs, original.attrs, present_[current_index].node);
        std::vector<std::size_t> pairs = *mark_pairs(current_index, original_index);
        for (std::size_t i = 0; i < current.marks.size(); ++i) {
            Mark& mark = current.marks[i];
            inherit_attrs(mark.attrs, original.marks[pairs[i]].attrs, present_[current_index].marks[i]);
        }
        for (std::size_t i = 0; i < current.content.size(); ++i) {
            fill(current.content[i], original.content[i]);
        }
    }

private:
    Document& document_;
    const Document& base_;
    const InputAttrKeys& present_;

    std::optional<std::vector<std::size_t>> mark_pairs(std::size_t current_index,
                                                      std::size_t original_index) const {
        const Node& current = document_.node(current_index);
        const Node& original = base_.node(original_index);
        if (current.marks.size() != original.marks.size()) {
            return std::nullopt;
        }
        std::vector<std::size_t> pairs;
        pairs.reserve(current.marks.size());
        std::vector<bool> used(original.marks.size());
        for (std::size_t i = 0; i < current.marks.size(); ++i) {
            const Mark& mark = current.marks[i];
            const MarkSpec& spec = *document_.schema().mark(mark.type);
            std::size_t j = 0;
            for (; j < original.marks.size(); ++j) {
                if (!used[j] && mark.type == original.marks[j].type &&
                    same_attrs(mark.attrs, original.marks[j].attrs, spec.attrs, present_[current_index].marks[i])) {
                    break;
                }
            }
            if (j == original.marks.size()) {
                return std::nullopt;
            }
            used[j] = true;
            pairs.push_back(j);
        }
        return pairs;
    }
};

}  // namespace

void inherit_attrs_and_spelling(Document& document, const Document& base, const InputAttrKeys& present) {
    const auto& original_children = base.root().content;
    const auto& children = document.root().content;
    std::unordered_map<std::size_t, std::vector<std::size_t>> candidates;
    candidates.reserve(original_children.size());
    for (std::size_t i = 0; i < original_children.size(); ++i) {
        candidates[block_hash(base, original_children[i])].push_back(i);
    }

    BlockComparison comparison(document, base, present);
    std::vector<bool> used(original_children.size());
    std::vector<std::optional<std::size_t>> matches(children.size());
    std::vector<std::optional<std::size_t>> positions(original_children.size());
    std::size_t next_ordered = 0;
    for (std::size_t i = 0; i < children.size(); ++i) {
        auto bucket = candidates.find(block_hash(document, children[i]));
        if (bucket == candidates.end()) {
            continue;
        }
        const auto& available = bucket->second;
        auto ordered = std::lower_bound(available.begin(), available.end(), next_ordered);
        auto match = [&](auto begin, auto end) {
            return std::find_if(begin, end, [&](std::size_t candidate) {
                return !used[candidate] && comparison.same(children[i], original_children[candidate]);
            });
        };
        auto found = match(ordered, available.end());
        if (found == available.end()) {
            found = match(available.begin(), ordered);
            if (found == ordered) {
                continue;
            }
        }
        std::size_t candidate = *found;
        used[candidate] = true;
        matches[i] = candidate;
        positions[candidate] = i;
        next_ordered = candidate + 1;
        comparison.fill(children[i], original_children[candidate]);
    }

    if (!base.spelling()) {
        return;
    }
    const Spelling& base_spelling = *base.spelling();
    std::vector<const SpellingPiece*> blocks;
    blocks.reserve(original_children.size());
    std::vector<std::vector<SpellingPiece>> trailing(children.size() + 1);
    std::size_t anchor = 0;
    for (const SpellingPiece& piece : base_spelling.items) {
        if (piece.has_node) {
            std::size_t index = blocks.size();
            blocks.push_back(&piece);
            if (positions[index]) {
                anchor = *positions[index] + 1;
            }
        } else {
            trailing[anchor].push_back(piece);
        }
    }

    document.spelling().emplace(base_spelling.source);
    Spelling& spelling = *document.spelling();
    spelling.head = base_spelling.head;
    spelling.html = base_spelling.html;
    spelling.cjk_friendly = base_spelling.cjk_friendly;
    spelling.items.reserve(base_spelling.items.size() + children.size());
    spelling.items.insert(spelling.items.end(), trailing[0].begin(), trailing[0].end());
    for (std::size_t i = 0; i < children.size(); ++i) {
        spelling.items.push_back(matches[i] ? *blocks[*matches[i]] : SpellingPiece {});
        spelling.items.insert(spelling.items.end(), trailing[i + 1].begin(), trailing[i + 1].end());
    }
}

}  // namespace marktip
