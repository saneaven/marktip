#include "schema_builder.h"

#include <algorithm>
#include <initializer_list>
#include <stdexcept>
#include <string_view>
#include <unordered_set>
#include <utility>

#include "tags.h"

namespace marktip {
namespace {

bool tag_name(std::string_view name) {
    if (name.empty() || !tag_name_start(name.front())) {
        return false;
    }
    return std::all_of(name.begin() + 1, name.end(), tag_name_char);
}

bool attr_name(std::string_view name) {
    if (name.empty() || !attr_name_start(name.front())) {
        return false;
    }
    return std::all_of(name.begin() + 1, name.end(), attr_name_char);
}

std::string ascii_lower(std::string value) {
    for (char& letter : value) {
        if (letter >= 'A' && letter <= 'Z') {
            letter = static_cast<char>(letter + ('a' - 'A'));
        }
    }
    return value;
}

bool value_type(const AttrValue& value, AttrRule rule) {
    return (rule == AttrRule::Str && value.kind == AttrValue::Kind::String) ||
           (rule == AttrRule::Int && value.kind == AttrValue::Kind::Int) ||
           (rule == AttrRule::Bool && value.kind == AttrValue::Kind::Bool) ||
           (rule == AttrRule::ColWidth && value.kind == AttrValue::Kind::IntList);
}

AttrSpec compile_attr(const AttrDeclaration& declaration) {
    if (!attr_name(declaration.name)) {
        throw std::invalid_argument("invalid attr name '" + declaration.name + "'");
    }
    if (declaration.choices) {
        for (const AttrValue& value : *declaration.choices) {
            if (!value_type(value, declaration.rule)) {
                throw std::invalid_argument("choices for attr '" + declaration.name + "' must match its type");
            }
        }
    }
    if (declaration.fallback && !value_type(*declaration.fallback, declaration.rule)) {
        throw std::invalid_argument("default for attr '" + declaration.name + "' must match its type");
    }
    if (declaration.fallback && declaration.choices &&
        std::find(declaration.choices->begin(), declaration.choices->end(), *declaration.fallback) ==
            declaration.choices->end()) {
        throw std::invalid_argument("default for attr '" + declaration.name + "' must be in choices");
    }
    if (declaration.required && declaration.fallback) {
        throw std::invalid_argument("attr '" + declaration.name + "' cannot have both required and default");
    }
    UriKind uri = UriKind::None;
    if (declaration.uri) {
        if (*declaration.uri != "link" && *declaration.uri != "image") {
            throw std::invalid_argument("uri for attr '" + declaration.name + "' must be 'link' or 'image'");
        }
        if (declaration.rule != AttrRule::Str) {
            throw std::invalid_argument("uri requires a str attr: '" + declaration.name + "'");
        }
        if (declaration.fallback) {
            throw std::invalid_argument("attr '" + declaration.name + "' cannot have both uri and default");
        }
        uri = *declaration.uri == "link" ? UriKind::Link : UriKind::Image;
    }
    return {declaration.name, declaration.rule, NullAttr::Unset, MarkdownForm::Carried,
            declaration.required ? Presence::Required : Presence::Optional, {},
            declaration.choices, declaration.fallback, uri};
}

std::vector<AttrSpec> compile_attrs(const std::vector<AttrDeclaration>& declarations) {
    std::vector<AttrSpec> specs;
    std::unordered_set<std::string> names;
    for (const AttrDeclaration& declaration : declarations) {
        if (!names.insert(declaration.name).second) {
            throw std::invalid_argument("duplicate attr name '" + declaration.name + "'");
        }
        specs.push_back(compile_attr(declaration));
    }
    return specs;
}

std::vector<std::size_t> core_tag_attrs(const std::vector<AttrSpec>& attrs,
                                      std::initializer_list<std::string_view> names) {
    std::vector<std::size_t> order;
    for (std::string_view name : names) {
        auto attr = std::find_if(attrs.begin(), attrs.end(), [&](const AttrSpec& spec) { return spec.name == name; });
        order.push_back(static_cast<std::size_t>(attr - attrs.begin()));
    }
    return order;
}

bool list_owner(std::string_view type) {
    return type == "bulletList" || type == "taskList" || type == "orderedList" ||
           type == "listItem" || type == "taskItem";
}

bool table_owner(std::string_view type) {
    return type == "table" || type == "tableRow" || type == "tableHeader" || type == "tableCell";
}

void merge_core_attrs(std::vector<AttrSpec>& attrs, std::vector<std::size_t>& order,
                      const CoreAttrDeclaration& declaration) {
    for (const AttrDeclaration& attr : declaration.attrs) {
        if (attr.required) {
            throw std::invalid_argument("core attr '" + declaration.type + "." + attr.name + "' cannot be required");
        }
    }
    for (AttrSpec& attr : compile_attrs(declaration.attrs)) {
        auto existing = std::find_if(attrs.begin(), attrs.end(), [&](const AttrSpec& spec) {
            return spec.name == attr.name;
        });
        if (existing != attrs.end() && existing->form != MarkdownForm::Dropped && existing->rule != AttrRule::NoSpan) {
            throw std::invalid_argument("core attr '" + declaration.type + "." + attr.name +
                                        "' is already carried by Markdown");
        }
        attr.form = MarkdownForm::Tag;
        if (existing == attrs.end()) {
            order.push_back(attrs.size());
            attrs.push_back(std::move(attr));
        } else {
            order.push_back(static_cast<std::size_t>(existing - attrs.begin()));
            *existing = std::move(attr);
        }
    }
}

std::vector<std::string> groups_from_declaration(const NodeDeclaration& declaration) {
    std::string_view group = declaration.group ? std::string_view(*declaration.group)
                                               : std::string_view(declaration.kind);
    std::vector<std::string> groups;
    std::size_t off = 0;
    while (off < group.size()) {
        off = group.find_first_not_of(" \t\n\r\f\v", off);
        if (off == std::string_view::npos) {
            break;
        }
        std::size_t end = group.find_first_of(" \t\n\r\f\v", off);
        if (end == std::string_view::npos) {
            end = group.size();
        }
        groups.emplace_back(group.substr(off, end - off));
        off = end;
    }
    return groups;
}

}  // namespace

std::shared_ptr<Schema> SchemaBuilder::build(std::vector<MarkDeclaration> marks, std::vector<NodeDeclaration> nodes,
                                             std::vector<CoreAttrDeclaration> core_attrs, bool block_image) {
    std::shared_ptr<Schema> schema(new Schema);
    schema->block_image_ = block_image;
    if (block_image) {
        auto image = std::find_if(schema->nodes_.begin(), schema->nodes_.end(), [](const NodeSpec& spec) {
            return spec.name == "image";
        });
        image->shape = Shape::BlockAtom;
        image->is_block = true;
        image->is_inline = false;
    }
    for (const CoreAttrDeclaration& declaration : core_attrs) {
        schema->list_tags_ = schema->list_tags_ || list_owner(declaration.type);
        schema->table_tags_ = schema->table_tags_ || table_owner(declaration.type);
    }
    for (NodeSpec& node : schema->nodes_) {
        if (schema->list_tags_ && list_owner(node.name)) {
            node.shape = Shape::BlockContainer;
            if (node.name == "listItem" || node.name == "taskItem") {
                node.tag = "li";
                if (node.name == "taskItem") {
                    node.tag_attrs = core_tag_attrs(node.attrs, {"checked"});
                }
            } else if (node.name == "orderedList") {
                node.tag = "ol";
                node.tag_attrs = core_tag_attrs(node.attrs, {"start", "tight"});
            } else {
                node.tag = "ul";
                node.tag_attrs = core_tag_attrs(node.attrs, {"tight"});
            }
        } else if (schema->table_tags_ && table_owner(node.name)) {
            node.shape = Shape::BlockContainer;
            if (node.name == "table") {
                node.tag = "table";
                node.tag_attrs = core_tag_attrs(node.attrs, {"colCount"});
            } else if (node.name == "tableRow") {
                node.tag = "tr";
            } else {
                node.tag = node.name == "tableHeader" ? "th" : "td";
                node.tag_attrs = core_tag_attrs(node.attrs, {"align"});
            }
        }
    }
    for (const CoreAttrDeclaration& declaration : core_attrs) {
        if (declaration.type == "link") {
            auto mark = std::find_if(schema->marks_.begin(), schema->marks_.end(), [](const MarkSpec& spec) {
                return spec.name == "link";
            });
            mark->tag_attrs = core_tag_attrs(mark->attrs, {"href", "title"});
            merge_core_attrs(mark->attrs, mark->tag_attrs, declaration);
            mark->tag = "a";
            schema->link_tag_ = true;
            schema->link_uri_ = std::any_of(mark->attrs.begin(), mark->attrs.end(), [&](const AttrSpec& attr) {
                return is_declared_uri_attr(attr, mark->core);
            });
        } else if (declaration.type == "paragraph" || declaration.type == "heading" || declaration.type == "image" ||
                   declaration.type == "blockquote" || list_owner(declaration.type) || table_owner(declaration.type)) {
            auto node = std::find_if(schema->nodes_.begin(), schema->nodes_.end(), [&](const NodeSpec& spec) {
                return spec.name == declaration.type;
            });
            if (declaration.type == "image") {
                node->tag_attrs = core_tag_attrs(node->attrs, {"src", "alt", "title"});
            }
            merge_core_attrs(node->attrs, node->tag_attrs, declaration);
            if (declaration.type == "paragraph") {
                node->tag = "p";
                node->shape = Shape::TextBlock;
            } else if (declaration.type == "heading") {
                node->tag = "h1";
                node->shape = Shape::TextBlock;
            } else if (declaration.type == "image") {
                node->tag = "img";
            } else if (declaration.type == "blockquote") {
                node->tag = "blockquote";
                node->shape = Shape::BlockContainer;
            }
        } else {
            throw std::invalid_argument("core attrs are not supported for type '" + declaration.type + "'");
        }
    }
    schema->core_attrs_ = !core_attrs.empty();
    std::unordered_set<std::string> names;
    std::unordered_set<std::string> mark_names;
    std::unordered_set<std::string> tags;
    const std::unordered_set<std::string> reserved_tags = {
        "pre", "script", "style", "textarea", "br", "p", "h1", "h2", "h3", "h4", "h5", "h6",
        "blockquote", "ul", "ol", "li", "table", "tr", "th", "td", "img", "a",
    };
    auto check_type_and_tag = [&](const std::string& name, const std::optional<std::string>& declared_tag,
                                   bool implicit) {
        if (schema->node(name) != nullptr || schema->mark(name) != nullptr || !names.insert(name).second) {
            throw std::invalid_argument("duplicate type name '" + name + "'");
        }
        if (implicit) {
            if (declared_tag) {
                throw std::invalid_argument("implicit node '" + name + "' must not declare a tag");
            }
            return;
        }
        const std::string& tag = declared_tag ? *declared_tag : name;
        if (!tag_name(tag)) {
            throw std::invalid_argument("invalid tag name '" + tag + "'");
        }
        std::string folded_tag = ascii_lower(tag);
        if (reserved_tags.find(folded_tag) != reserved_tags.end()) {
            throw std::invalid_argument("reserved tag name '" + tag + "'");
        }
        if (!tags.insert(std::move(folded_tag)).second) {
            throw std::invalid_argument("duplicate tag name '" + tag + "'");
        }
    };
    for (const MarkDeclaration& declaration : marks) {
        check_type_and_tag(declaration.name, declaration.tag, false);
        mark_names.insert(declaration.name);
    }
    for (const NodeDeclaration& declaration : nodes) {
        check_type_and_tag(declaration.name, declaration.tag, declaration.implicit);
    }
    std::size_t order = 0;
    for (const MarkDeclaration& declaration : marks) {
        MarkSpec mark;
        mark.name = declaration.name;
        mark.core = false;
        mark.tag = declaration.tag ? *declaration.tag : declaration.name;
        mark.order = order++;
        mark.attrs = compile_attrs(declaration.attrs);
        if (std::holds_alternative<std::monostate>(declaration.excludes)) {
            mark.excludes.names.push_back(mark.name);
        } else if (const auto* all = std::get_if<std::string>(&declaration.excludes)) {
            if (*all != "_") {
                throw std::invalid_argument("excludes must be None, '_', or a tuple of mark names");
            }
            mark.excludes.all = true;
        } else {
            mark.excludes.names = std::get<std::vector<std::string>>(declaration.excludes);
            for (const std::string& name : mark.excludes.names) {
                if (Schema::gfm()->mark(name) == nullptr && mark_names.find(name) == mark_names.end()) {
                    throw std::invalid_argument("excludes names unknown mark '" + name + "'");
                }
            }
        }
        schema->marks_.push_back(std::move(mark));
    }
    std::vector<ContentType> content_types;
    for (const NodeSpec& node : schema->nodes_) {
        ContentType type {node.name, node.is_inline, {}};
        if (node.is_block) {
            type.groups.push_back("block");
        }
        if (node.is_inline) {
            type.groups.push_back("inline");
        }
        content_types.push_back(std::move(type));
    }
    std::size_t core_nodes = schema->nodes_.size();
    for (const NodeDeclaration& declaration : nodes) {
        if (declaration.kind != "inline" && declaration.kind != "block") {
            throw std::invalid_argument("unsupported node kind '" + declaration.kind + "'");
        }
        std::vector<std::string> groups = groups_from_declaration(declaration);
        if (declaration.implicit && !declaration.attrs.empty()) {
            throw std::invalid_argument("implicit node '" + declaration.name + "' must not declare attrs");
        }
        if (declaration.implicit && !groups.empty()) {
            throw std::invalid_argument("implicit node '" + declaration.name + "' must not declare groups");
        }
        bool is_block = std::find(groups.begin(), groups.end(), "block") != groups.end();
        bool is_inline = std::find(groups.begin(), groups.end(), "inline") != groups.end();
        // Core block models read this membership directly,
        // so an inline shape here would be written as a block and read back inside a paragraph.
        if (declaration.kind == "inline" && is_block) {
            throw std::invalid_argument("inline node '" + declaration.name + "' cannot join block group");
        }
        if (declaration.kind == "block" && is_inline) {
            throw std::invalid_argument("block node '" + declaration.name + "' cannot join inline group");
        }
        Shape shape = declaration.kind == "inline" ? Shape::InlineAtom : Shape::BlockAtom;
        if (declaration.content && !declaration.content->empty()) {
            shape = declaration.kind == "inline" ? Shape::InlineContainer : Shape::BlockContainer;
        }
        schema->nodes_.push_back({declaration.name, compile_attrs(declaration.attrs), ContentModel::None,
                                  is_block, is_inline, false, declaration.implicit,
                                  declaration.implicit ? std::string {} :
                                      declaration.tag ? *declaration.tag : declaration.name,
                                  shape});
        content_types.push_back({declaration.name, declaration.kind == "inline", std::move(groups)});
        if (shape == Shape::InlineContainer) {
            schema->inline_containers_ = true;
        }
    }
    for (std::size_t i = 0; i < nodes.size(); ++i) {
        if (!nodes[i].content || nodes[i].content->empty()) {
            continue;
        }
        ContentDFA content = compile_content(*nodes[i].content, content_types);
        if (nodes[i].kind == "inline" && content.inline_content == false) {
            throw std::invalid_argument("inline node '" + nodes[i].name + "' cannot contain block content");
        }
        // Markdown does not carry the boundaries between adjacent text or raw HTML nodes.
        if (!content.idempotent("text") || !content.idempotent("htmlInline")) {
            throw std::invalid_argument(
                "content expression must not depend on how many adjacent text nodes there are; "
                "use text* or text+ (and htmlInline* or htmlInline+)");
        }
        if (nodes[i].kind == "block" && content.inline_content == true) {
            schema->nodes_[core_nodes + i].shape = Shape::TextBlock;
        }
        schema->nodes_[core_nodes + i].dfa = static_cast<int>(schema->content_.size());
        schema->content_.push_back(std::move(content));
    }
    std::unordered_set<std::string> fence_words;
    std::unordered_set<std::string> math_modes;
    for (std::size_t i = 0; i < nodes.size(); ++i) {
        const NodeDeclaration& declaration = nodes[i];
        NodeSpec& node = schema->nodes_[core_nodes + i];
        if ((declaration.fence || declaration.math) && !declaration.body) {
            throw std::invalid_argument("node '" + node.name + "' requires body for its fence or math carrier");
        }
        if (declaration.body) {
            auto attr = std::find_if(node.attrs.begin(), node.attrs.end(), [&](const AttrSpec& spec) {
                return spec.name == *declaration.body;
            });
            if (attr == node.attrs.end() || attr->rule != AttrRule::Str) {
                throw std::invalid_argument("body for node '" + node.name + "' must name a declared str attr");
            }
            node.body = static_cast<int>(attr - node.attrs.begin());
        }
        if (declaration.fence) {
            if (node.shape != Shape::BlockAtom) {
                throw std::invalid_argument("fence carrier requires a block atom: '" + node.name + "'");
            }
            if (!fence_words.insert(*declaration.fence).second) {
                throw std::invalid_argument("duplicate fence word '" + *declaration.fence + "'");
            }
            node.fence = *declaration.fence;
        }
        if (declaration.math) {
            if (*declaration.math == "inline") {
                node.math = MathMode::Inline;
            } else if (*declaration.math == "display") {
                node.math = MathMode::Display;
            } else {
                throw std::invalid_argument("math must be 'inline' or 'display'");
            }
            Shape required = node.math == MathMode::Inline ? Shape::InlineAtom : Shape::BlockAtom;
            if (node.shape != required) {
                throw std::invalid_argument("math carrier has an incompatible shape for node '" + node.name + "'");
            }
            if (!math_modes.insert(*declaration.math).second) {
                throw std::invalid_argument("duplicate math mode '" + *declaration.math + "'");
            }
        }
    }
    schema->declared_marks_ = !marks.empty();
    schema->declared_nodes_ = !nodes.empty();
    std::sort(schema->nodes_.begin(), schema->nodes_.end(),
              [](const NodeSpec& left, const NodeSpec& right) { return left.name < right.name; });
    for (const NodeSpec& node : schema->nodes_) {
        if (node.implicit && (node.dfa < 0 || schema->content_[node.dfa].inline_content != false)) {
            throw std::invalid_argument("implicit node '" + node.name + "' must have block content");
        }
    }
    for (const NodeSpec& node : schema->nodes_) {
        if (node.dfa < 0) {
            continue;
        }
        ContentDFA& parent = schema->content_[node.dfa];
        for (const std::string& type : parent.referenced_types) {
            const NodeSpec& child = *schema->node(type);
            if (!child.implicit) {
                continue;
            }
            if (node.implicit) {
                throw std::invalid_argument("implicit node '" + node.name + "' must not contain implicit node '" +
                                            type + "'");
            }
            if (!parent.required_once(type)) {
                throw std::invalid_argument("implicit node '" + type + "' must occur exactly once without "
                                            "repetition or optionality in content of node '" + node.name + "'");
            }
            const ContentDFA& wrapped = schema->content_[child.dfa];
            for (const ContentDFA::State& state : wrapped.states) {
                for (const ContentDFA::Transition& transition : state.transitions) {
                    if (parent.accepts_type(transition.type)) {
                        throw std::invalid_argument("implicit node '" + type + "' and parent node '" + node.name +
                                                    "' accept the same child type '" + transition.type + "'");
                    }
                    for (const std::string& earlier : parent.implicit_types) {
                        const ContentDFA& other = schema->content_[schema->node(earlier)->dfa];
                        if (other.accepts_type(transition.type)) {
                            throw std::invalid_argument("implicit nodes '" + earlier + "' and '" + type +
                                                        "' accept the same child type '" + transition.type + "'");
                        }
                    }
                }
            }
            parent.implicit_types.push_back(type);
        }
    }
    schema->minimum_.clear();
    schema->minimum_.resize(schema->nodes_.size());
    schema->creatable_.clear();
    const Schema& core = *Schema::gfm();
    for (std::size_t i = 0; i < schema->nodes_.size(); ++i) {
        const NodeSpec& node = schema->nodes_[i];
        if (node.core) {
            const auto* minimum = core.minimum_content(*core.node(node.name));
            if (minimum != nullptr) {
                schema->minimum_[i] = *minimum;
                schema->creatable_.push_back(node.name);
            }
        } else if (std::none_of(node.attrs.begin(), node.attrs.end(), [](const AttrSpec& attr) {
                       return attr.presence == Presence::Required;
                   }) && (node.dfa < 0 || schema->content_[node.dfa].states[0].accepting)) {
            schema->minimum_[i].emplace();
            schema->creatable_.push_back(node.name);
        }
    }
    while (true) {
        std::vector<std::pair<std::size_t, std::vector<std::string>>> ready;
        for (std::size_t i = 0; i < schema->nodes_.size(); ++i) {
            const NodeSpec& node = schema->nodes_[i];
            if (node.core || schema->minimum_[i] ||
                std::any_of(node.attrs.begin(), node.attrs.end(), [](const AttrSpec& attr) {
                    return attr.presence == Presence::Required;
                })) {
                continue;
            }
            auto filled = schema->content_[node.dfa].fill({}, schema->creatable_);
            if (!filled) {
                continue;
            }
            std::vector<std::string> minimum;
            for (ContentFill& child : *filled) {
                minimum.push_back(std::move(child.type));
            }
            ready.emplace_back(i, std::move(minimum));
        }
        if (ready.empty()) {
            break;
        }
        for (auto& node : ready) {
            schema->minimum_[node.first] = std::move(node.second);
            schema->creatable_.push_back(schema->nodes_[node.first].name);
        }
    }
    // A preferred alternative can become creatable after the first witness for its parent.
    // Select against the completed set before checking whether those choices create a cycle.
    for (const std::string& type : schema->creatable_) {
        std::size_t index = schema->node(type) - schema->nodes_.data();
        const NodeSpec& node = schema->nodes_[index];
        if (node.dfa < 0) {
            continue;
        }
        auto filled = schema->content_[node.dfa].fill({}, schema->creatable_);
        std::vector<std::string> minimum;
        for (ContentFill& child : *filled) {
            minimum.push_back(std::move(child.type));
        }
        schema->minimum_[index] = std::move(minimum);
    }
    struct CreationFrame {
        std::size_t node;
        std::size_t next = 0;
    };
    std::vector<unsigned char> visited(schema->nodes_.size());
    for (const std::string& type : schema->creatable_) {
        std::size_t index = schema->node(type) - schema->nodes_.data();
        if (visited[index] != 0) {
            continue;
        }
        std::vector<CreationFrame> frames {{index}};
        visited[index] = 1;
        while (!frames.empty()) {
            CreationFrame& frame = frames.back();
            const auto& minimum = *schema->minimum_[frame.node];
            if (frame.next == minimum.size()) {
                visited[frame.node] = 2;
                frames.pop_back();
                continue;
            }
            const NodeSpec* child = schema->node(minimum[frame.next++]);
            std::size_t child_index = child - schema->nodes_.data();
            if (visited[child_index] == 1) {
                throw std::invalid_argument("content fill for node '" + child->name + "' would create itself");
            }
            if (visited[child_index] == 0) {
                visited[child_index] = 1;
                frames.push_back({child_index});
            }
        }
    }
    std::sort(schema->marks_.begin(), schema->marks_.end(),
              [](const MarkSpec& left, const MarkSpec& right) { return left.name < right.name; });
    for (std::size_t i = 0; i < schema->marks_.size(); ++i) {
        const MarkSpec& mark = schema->marks_[i];
        schema->uri_attrs_ = schema->uri_attrs_ ||
                             std::any_of(mark.attrs.begin(), mark.attrs.end(), [&](const AttrSpec& attr) {
                                 return is_declared_uri_attr(attr, mark.core);
                             });
        if (!mark.tag.empty()) {
            schema->tags_.push_back({mark.tag, true, false, i});
        }
    }
    for (std::size_t i = 0; i < schema->nodes_.size(); ++i) {
        const NodeSpec& node = schema->nodes_[i];
        schema->uri_attrs_ = schema->uri_attrs_ ||
                             std::any_of(node.attrs.begin(), node.attrs.end(), [&](const AttrSpec& attr) {
                                 return is_declared_uri_attr(attr, node.core);
                             });
        schema->textblock_tags_ = schema->textblock_tags_ ||
                                  (!node.tag.empty() && node.shape == Shape::TextBlock);
        if (!node.tag.empty() && !(node.core && (node.name == "taskList" || node.name == "taskItem"))) {
            if (node.name == "heading" && node.core) {
                for (char level = '1'; level <= '6'; ++level) {
                    schema->tags_.push_back({std::string("h") + level, false, false, i});
                }
            } else {
                schema->tags_.push_back({node.tag, false,
                                          node.shape == Shape::BlockAtom || node.shape == Shape::BlockContainer, i});
            }
        }
        if (!node.fence.empty()) {
            schema->fences_.push_back({node.fence, i});
        }
        if (node.math == MathMode::Inline) {
            schema->inline_math_ = static_cast<int>(i);
        } else if (node.math == MathMode::Display) {
            schema->display_math_ = static_cast<int>(i);
        }
    }
    std::sort(schema->tags_.begin(), schema->tags_.end(),
              [](const TagEntry& left, const TagEntry& right) { return left.tag < right.tag; });
    std::sort(schema->fences_.begin(), schema->fences_.end(),
              [](const Schema::FenceEntry& left, const Schema::FenceEntry& right) { return left.word < right.word; });
    return schema;
}

}  // namespace marktip
