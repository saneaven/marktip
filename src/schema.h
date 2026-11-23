#pragma once

#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "content.h"
#include "value.h"

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
    Int,
    Level,      // int 1..6
    ListStart,  // int 0..kMaxListStart
    Count,      // int >= 0
    Align,      // "left" | "center" | "right" | None
    Size,       // str or int: Tiptap parses width/height out of HTML as a str, apps store an int
    ColWidth,   // list of ints
    NoSpan,     // int == 1: GFM tables have no cell spanning
    StrMap,     // ordered string map
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
    Tag,
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

enum class UriKind { None, Link, Image };

struct AttrSpec {
    std::string name;
    AttrRule rule;
    NullAttr null = NullAttr::Refused;
    MarkdownForm form = MarkdownForm::Carried;
    Presence presence = Presence::Optional;
    std::string why = {};  // Dropped only: the reason Exact reports
    std::optional<std::vector<AttrValue>> choices = std::nullopt;
    std::optional<AttrValue> fallback = std::nullopt;
    UriKind uri = UriKind::None;
    // A mark replacing an open mark of its own type takes this attr from it, unless its own tag writes one.
    bool inherit = false;
};

bool is_declared_uri_attr(const AttrSpec& attr, bool core);
bool attr_is_carried(const AttrSpec& attr);

enum class Shape { InlineAtom, InlineContainer, BlockAtom, BlockContainer, TextBlock };
enum class MathMode { None, Inline, Display };

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
    bool core = true;
    bool implicit = false;
    std::string tag = {};
    Shape shape = Shape::InlineAtom;
    int dfa = -1;
    std::string fence = {};
    MathMode math = MathMode::None;
    int body = -1;
    std::vector<std::size_t> tag_attrs = {};
};

struct ExcludeSet {
    bool all = false;
    std::vector<std::string> names = {};
};

struct MarkSpec {
    std::string name;
    std::vector<AttrSpec> attrs;
    bool core = true;
    std::string tag = {};
    ExcludeSet excludes = {};
    std::size_t order = 0;
    std::vector<std::size_t> tag_attrs = {};
};

struct TagEntry {
    std::string tag;
    bool is_mark;
    bool block_line = false;
    std::size_t spec;
};

class Schema {
public:
    static const std::shared_ptr<const Schema>& gfm();

    const NodeSpec* node(std::string_view type) const;
    const NodeSpec& node(std::size_t index) const;
    const MarkSpec* mark(std::string_view type) const;
    const MarkSpec& mark(std::size_t index) const;
    const ContentDFA& content(int index) const;
    const std::vector<std::string>& creatable_types() const;
    const std::vector<std::string>* minimum_content(const NodeSpec& spec) const;
    const TagEntry* tag(std::string_view name) const;
    const std::vector<TagEntry>& tags() const;
    bool has_tags() const;
    bool has_declared_marks() const;
    bool has_declared_nodes() const;
    bool has_core_attrs() const;
    bool has_node_forms() const;
    bool has_link_tag() const;
    bool has_link_uri() const;
    bool has_uri_attrs() const;
    bool has_textblock_tags() const;
    bool has_list_tags() const;
    bool has_table_tags() const;
    bool block_image() const;
    const std::string& fingerprint() const;
    bool has_fences() const;
    const NodeSpec* fence(std::string_view word) const;
    bool has_math() const;
    const NodeSpec* inline_math() const;
    const NodeSpec* display_math() const;

    bool content_model_allows(ContentModel model, const NodeSpec& child) const;

private:
    friend class SchemaBuilder;
    Schema();

    struct FenceEntry {
        std::string word;
        std::size_t spec;
    };

    std::vector<NodeSpec> nodes_;
    std::vector<MarkSpec> marks_;
    std::vector<ContentDFA> content_;
    std::vector<std::optional<std::vector<std::string>>> minimum_;
    std::vector<std::string> creatable_;
    std::vector<TagEntry> tags_;
    bool declared_marks_ = false;
    bool declared_nodes_ = false;
    bool core_attrs_ = false;
    std::vector<FenceEntry> fences_;
    int inline_math_ = -1;
    int display_math_ = -1;
    bool link_tag_ = false;
    bool link_uri_ = false;
    bool uri_attrs_ = false;
    bool textblock_tags_ = false;
    bool list_tags_ = false;
    bool table_tags_ = false;
    bool block_image_ = false;
    std::string fingerprint_;
};

}  // namespace marktip
