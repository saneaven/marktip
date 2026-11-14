#include "schema.h"

#include <algorithm>

namespace marktip {

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

const MarkSpec* Schema::mark(std::string_view type) const {
    auto found = std::lower_bound(marks_.begin(), marks_.end(), type,
                                  [](const MarkSpec& spec, std::string_view name) { return spec.name < name; });
    if (found == marks_.end() || found->name != type) {
        return nullptr;
    }
    return &*found;
}

bool Schema::has_declared_marks() const {
    return marks_.size() != gfm()->marks_.size();
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
