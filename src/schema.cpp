#include "schema.h"

#include <algorithm>

namespace marktip {

bool is_declared_uri_attr(const AttrSpec& attr, bool core) {
    return attr.uri != UriKind::None && (!core || attr.form == MarkdownForm::Tag);
}

Schema::Schema() {
    // The sentences Exact reports for a Dropped attr, shared by the specs that mean the same thing.
    const char* no_link_presentation = "a markdown link carries only a destination and a title";
    const char* no_image_size = "markdown images carry no dimensions";

    const std::vector<AttrSpec> heading_attrs = {{"level", AttrRule::Level}};
    const std::vector<AttrSpec> code_block_attrs = {{"info", AttrRule::InfoStr, NullAttr::Unset},
                                                 {"language", AttrRule::InfoStr, NullAttr::Unset}};
    const std::vector<AttrSpec> tight_attrs = {{"tight", AttrRule::Bool}};
    const std::vector<AttrSpec> ordered_list_attrs = {
        {"start", AttrRule::ListStart},
        {"tight", AttrRule::Bool},
        {"type", AttrRule::Str, NullAttr::Unset, MarkdownForm::Dropped, Presence::Optional,
         "markdown ordered lists are always numeric"},
    };
    const std::vector<AttrSpec> task_item_attrs = {{"checked", AttrRule::Bool}};
    const std::vector<AttrSpec> table_attrs = {{"colCount", AttrRule::Count, NullAttr::Unset}};
    const std::vector<AttrSpec> cell_attrs = {
        {"align", AttrRule::Align},
        {"colspan", AttrRule::NoSpan},
        {"colwidth", AttrRule::ColWidth, NullAttr::Unset, MarkdownForm::Dropped, Presence::Optional,
         "GFM tables have no column widths"},
        {"rowspan", AttrRule::NoSpan},
    };
    const std::vector<AttrSpec> image_attrs = {
        {"alt", AttrRule::Str, NullAttr::Unset},
        {"height", AttrRule::Size, NullAttr::Unset, MarkdownForm::Dropped, Presence::Optional, no_image_size},
        {"src", AttrRule::Str, NullAttr::Unset, MarkdownForm::Carried, Presence::Required, {},
         std::nullopt, std::nullopt, UriKind::Image},
        {"title", AttrRule::Str, NullAttr::Unset},
        {"width", AttrRule::Size, NullAttr::Unset, MarkdownForm::Dropped, Presence::Optional, no_image_size},
    };
    const std::vector<AttrSpec> html_attrs = {{"html", AttrRule::Str}};
    const std::vector<AttrSpec> link_attrs = {
        {"class", AttrRule::Str, NullAttr::Unset, MarkdownForm::Dropped, Presence::Optional, no_link_presentation},
        {"href", AttrRule::Str, NullAttr::Unset, MarkdownForm::Carried, Presence::Required, {},
         std::nullopt, std::nullopt, UriKind::Link},
        {"rel", AttrRule::Str, NullAttr::Unset, MarkdownForm::Dropped, Presence::Optional, no_link_presentation},
        {"target", AttrRule::Str, NullAttr::Unset, MarkdownForm::Dropped, Presence::Optional, no_link_presentation},
        {"title", AttrRule::Str, NullAttr::Unset},
    };

    // The closed schema: every node/mark type the parser can emit and the serializer understands.
    // Sorted byte-wise (uppercase sorts before lowercase,
    // e.g. tableCell < tableHeader < tableRow) — required by binary_search;
    // do not "alphabetize" case-insensitively.
    nodes_ = {
        {"blockquote", {}, ContentModel::Blocks, true, false},
        {"bulletList", tight_attrs, ContentModel::ListItems, true, false},
        {"codeBlock", code_block_attrs, ContentModel::Text, true, false},
        {"doc", {}, ContentModel::Blocks, false, false},
        {"hardBreak", {}, ContentModel::None, false, true},
        {"heading", heading_attrs, ContentModel::Inlines, true, false},
        {"horizontalRule", {}, ContentModel::None, true, false},
        {"htmlBlock", html_attrs, ContentModel::None, true, false},
        {"htmlInline", html_attrs, ContentModel::None, false, true},
        {"image", image_attrs, ContentModel::None, false, true},
        {"listItem", {}, ContentModel::Blocks, false, false},
        {"orderedList", ordered_list_attrs, ContentModel::OrderedListItems, true, false},
        {"paragraph", {}, ContentModel::Inlines, true, false},
        {"table", table_attrs, ContentModel::Rows, true, false},
        {"tableCell", cell_attrs, ContentModel::Blocks, false, false},
        {"tableHeader", cell_attrs, ContentModel::Blocks, false, false},
        {"tableRow", {}, ContentModel::Cells, false, false},
        {"taskItem", task_item_attrs, ContentModel::Blocks, false, false},
        {"taskList", tight_attrs, ContentModel::TaskItems, true, false},
        {"text", {}, ContentModel::None, false, true},
    };
    minimum_.resize(nodes_.size());
    const NodeSpec* paragraph = node("paragraph");
    minimum_[paragraph - nodes_.data()].emplace();
    creatable_.push_back(paragraph->name);

    marks_ = {
        {"bold", {}},
        {"code", {}},
        {"italic", {}},
        {"link", link_attrs},
        {"strike", {}},
    };
    for (MarkSpec& mark : marks_) {
        mark.excludes.names.push_back(mark.name);
    }
}

const std::shared_ptr<const Schema>& Schema::gfm() {
    static const std::shared_ptr<const Schema> schema(new Schema);
    return schema;
}

const NodeSpec* Schema::node(std::string_view type) const {
    auto found = std::lower_bound(nodes_.begin(), nodes_.end(), type,
                                  [](const NodeSpec& spec, std::string_view name) { return spec.name < name; });
    if (found == nodes_.end() || found->name != type) {
        return nullptr;
    }
    return &*found;
}

const NodeSpec& Schema::node(std::size_t index) const {
    return nodes_[index];
}

const MarkSpec* Schema::mark(std::string_view type) const {
    auto found = std::lower_bound(marks_.begin(), marks_.end(), type,
                                  [](const MarkSpec& spec, std::string_view name) { return spec.name < name; });
    if (found == marks_.end() || found->name != type) {
        return nullptr;
    }
    return &*found;
}

bool Schema::has_declared_marks() const {
    return declared_marks_;
}

bool Schema::has_declared_nodes() const {
    return declared_nodes_;
}

bool Schema::has_core_attrs() const {
    return core_attrs_;
}

bool Schema::has_link_tag() const {
    return link_tag_;
}

bool Schema::has_link_uri() const {
    return link_uri_;
}

bool Schema::has_uri_attrs() const {
    return uri_attrs_;
}

bool Schema::has_textblock_tags() const {
    return textblock_tags_;
}

bool Schema::has_list_tags() const {
    return list_tags_;
}

bool Schema::has_table_tags() const {
    return table_tags_;
}

bool Schema::block_image() const {
    return block_image_;
}

bool Schema::has_inline_containers() const {
    return inline_containers_;
}

bool Schema::has_fences() const {
    return !fences_.empty();
}

const NodeSpec* Schema::fence(std::string_view word) const {
    auto found = std::lower_bound(fences_.begin(), fences_.end(), word,
                                  [](const FenceEntry& entry, std::string_view value) { return entry.word < value; });
    if (found == fences_.end() || found->word != word) {
        return nullptr;
    }
    return &nodes_[found->spec];
}

bool Schema::has_math() const {
    return inline_math_ >= 0 || display_math_ >= 0;
}

const NodeSpec* Schema::inline_math() const {
    return inline_math_ < 0 ? nullptr : &nodes_[inline_math_];
}

const NodeSpec* Schema::display_math() const {
    return display_math_ < 0 ? nullptr : &nodes_[display_math_];
}

const MarkSpec& Schema::mark(std::size_t index) const {
    return marks_[index];
}

const ContentDFA& Schema::content(int index) const {
    return content_[index];
}

const std::vector<std::string>& Schema::creatable_types() const {
    return creatable_;
}

const std::vector<std::string>* Schema::minimum_content(const NodeSpec& spec) const {
    const auto& minimum = minimum_[&spec - nodes_.data()];
    return minimum ? &*minimum : nullptr;
}

const TagEntry* Schema::tag(std::string_view name) const {
    auto found = std::lower_bound(tags_.begin(), tags_.end(), name,
                                  [](const TagEntry& entry, std::string_view value) { return entry.tag < value; });
    if (found == tags_.end() || found->tag != name) {
        return nullptr;
    }
    return &*found;
}

const std::vector<TagEntry>& Schema::tags() const {
    return tags_;
}

bool Schema::has_tags() const {
    return !tags_.empty();
}

bool Schema::content_model_allows(ContentModel model, const NodeSpec& child) const {
    switch (model) {
        case ContentModel::None:
            return false;
        case ContentModel::Blocks:
            return child.is_block;
        case ContentModel::Inlines:
            return child.is_inline;
        case ContentModel::Text:
            return child.name == "text";
        case ContentModel::ListItems:
            return child.name == "listItem";
        case ContentModel::OrderedListItems:
            // MD4C preserves an ordered task marker as orderedList -> taskItem;
            // this has been part of marktip's public parser/serializer grammar
            // since before strict content-model validation was introduced.
            return child.name == "listItem" || child.name == "taskItem";
        case ContentModel::TaskItems:
            return child.name == "taskItem";
        case ContentModel::Rows:
            return child.name == "tableRow";
        case ContentModel::Cells:
            return child.name == "tableHeader" || child.name == "tableCell";
    }
    return false;
}

}  // namespace marktip
