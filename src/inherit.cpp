#include "inherit.h"

#include <algorithm>
#include <optional>
#include <unordered_map>
#include <utility>

#include "schema.h"

namespace marktip {
namespace {

bool has_key(const AttrKeys& keys, const std::string& name) {
    return std::find(keys.begin(), keys.end(), name) != keys.end();
}

bool same_attrs(const AttrList& current, const AttrList& original, const std::vector<AttrSpec>& specs,
                const AttrKeys& present) {
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

void inherit_attrs(AttrList& current, const AttrList& original, const AttrKeys& present) {
    for (const auto& attr : original) {
        if (!has_key(present, attr.first)) {
            set_attr(current, attr.first, attr.second);
        }
    }
}

struct MarkPair {
    std::size_t original;
    const AttrKeys* present;
};

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
        std::vector<MarkPair> pairs = *mark_pairs(current_index, original_index);
        for (std::size_t i = 0; i < current.marks.size(); ++i) {
            Mark& mark = current.marks[i];
            inherit_attrs(mark.attrs, original.marks[pairs[i].original].attrs, *pairs[i].present);
        }
        for (std::size_t i = 0; i < current.content.size(); ++i) {
            fill(current.content[i], original.content[i]);
        }
    }

private:
    Document& document_;
    const Document& base_;
    const InputAttrKeys& present_;

    std::optional<std::vector<MarkPair>> mark_pairs(std::size_t current_index, std::size_t original_index) const {
        const Node& current = document_.node(current_index);
        const Node& original = base_.node(original_index);
        if (current.marks.size() != original.marks.size()) {
            return std::nullopt;
        }
        std::vector<MarkPair> pairs;
        pairs.reserve(current.marks.size());
        std::vector<bool> used(original.marks.size());
        const auto& input_marks = present_[current_index].marks;
        for (auto it = current.marks.begin(); it != current.marks.end(); ++it) {
            const Mark& mark = *it;
            const MarkSpec& spec = *document_.schema().mark(mark.type);
            auto occurrence = std::count_if(current.marks.begin(), it, [&](const Mark& previous) {
                return previous.type == mark.type;
            });
            auto input_mark = std::find_if(input_marks.begin(), input_marks.end(), [&](const auto& entry) {
                return entry.first == mark.type && occurrence-- == 0;
            });
            const AttrKeys& present = input_mark->second;
            std::size_t j = 0;
            for (; j < original.marks.size(); ++j) {
                if (!used[j] && mark.type == original.marks[j].type &&
                    same_attrs(mark.attrs, original.marks[j].attrs, spec.attrs, present)) {
                    break;
                }
            }
            if (j == original.marks.size()) {
                return std::nullopt;
            }
            used[j] = true;
            pairs.push_back({j, &present});
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
    spelling.items.reserve(base_spelling.items.size() + children.size());
    spelling.items.insert(spelling.items.end(), trailing[0].begin(), trailing[0].end());
    for (std::size_t i = 0; i < children.size(); ++i) {
        spelling.items.push_back(matches[i] ? *blocks[*matches[i]] : SpellingPiece {});
        spelling.items.insert(spelling.items.end(), trailing[i + 1].begin(), trailing[i + 1].end());
    }
}

}  // namespace marktip
