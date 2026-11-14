#pragma once

#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace marktip {

// Marktip's canonical child grammar for each known node,
// reduced to the categories strict validation needs to distinguish.
enum class ContentModel {
    None,
    Blocks,
    Inlines,
    Text,
    ListItems,
    OrderedListItems,
    TaskItems,
    Rows,
    Cells,
};

enum class AttrRule {
    Str,        // any str
    InfoStr,    // str, single line: a code fence info string cannot wrap
    Bool,
    Level,      // int 1..6
    ListStart,  // int 0..kMaxListStart
    Count,      // int >= 0
    Align,      // "left" | "center" | "right" | None
    Size,       // str or int: Tiptap parses width/height out of HTML as a str, apps store an int
    ColWidth,   // list of ints
    NoSpan,     // int == 1: GFM tables have no cell spanning
};

// A second axis, orthogonal to the value grammar: what a None means for this attr.
//
// ProseMirror serializes every attr in the schema, defaults included,
// and Tiptap declares `default: null` for most of what it puts on a node.
// A None on one of those is not a wrongly typed value,
// it is the attr never having been set — the absent-key case,
// which is accepted already and renders the same markdown either way.
// attrs_from_py keeps no None at all,
// so the two really are one case everywhere downstream: strict, the serializer, and the URI policy.
//
// Refused stays the default wherever Tiptap's default is not null (level, start, tight, checked, colspan):
// a null there is a caller mistake, not an unset attr.
// So is html, which is marktip's own attr with no Tiptap counterpart.
//
// Align is untouched: that rule takes None as a *value* ("no alignment") rather than as an unset marker.
enum class NullAttr {
    Refused,  // the default
    Unset,    // None accepted: the attr was never set
};

// A third axis: can markdown carry this attr at all.
//
// Dropped is the presentation an editor stamps onto a node with no markdown counterpart.
// Losing one costs the *author* nothing — nobody wrote it —
// which is why Content lets it through while still refusing a colspan,
// whose loss shifts every cell after it under a different header.
// Exact refuses both, and reports `why` when it does.
enum class MarkdownForm {
    Carried,  // the default
    Dropped,
};

// A fourth: must this attr be there for the node to mean anything.
//
// A link with no href and an image with no src have no valid unset state.
// The serializer would write "[a]()", which is not a lossy conversion but an invented one:
// it survives into stored markdown and reads back as a real link.
enum class Presence {
    Optional,  // the default
    Required,
};

struct AttrSpec {
    std::string name;
    AttrRule rule;
    NullAttr null = NullAttr::Refused;
    MarkdownForm form = MarkdownForm::Carried;
    Presence presence = Presence::Optional;
    std::string why = {};  // Dropped only: the reason Exact reports
};

struct NodeSpec {
    std::string name;
    std::vector<AttrSpec> attrs;
    ContentModel allow;
    // Membership in the "block nodes" and "inline nodes" child sets, respectively.
    // ContentModel::Blocks and ContentModel::Inlines accept those sets; this does not mean block-level status.
    // doc, listItem, taskItem, tableRow, tableCell, and tableHeader are deliberately in neither;
    // they have children but may only appear under the parent that names them.
    bool is_block;
    bool is_inline;
};

struct MarkSpec {
    std::string name;
    std::vector<AttrSpec> attrs;
};

class Schema {
public:
    static const std::shared_ptr<const Schema>& gfm();

    const NodeSpec* node(std::string_view type) const;
    const MarkSpec* mark(std::string_view type) const;

    bool content_model_allows(ContentModel model, const NodeSpec& child) const;

private:
    Schema();

    std::vector<NodeSpec> nodes_;
    std::vector<MarkSpec> marks_;
};

}  // namespace marktip
