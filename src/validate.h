#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

#include "path.h"
#include "schema.h"
#include "value.h"

namespace marktip {

struct Node;
class Document;

// What `strict` promises to preserve, rather than what it happens to accept.
//
// Content sits in the middle because losses are not all one kind:
// a colspan the serializer drops moves every cell after it under a different header,
// while a link target it drops costs the author nothing —
// the editor stamped that one on, and no one wrote it.
// Nothing in the JSON tells those apart (ProseMirror serializes schema defaults onto every node),
// so the caller has to say which loss is acceptable.
enum class StrictMode {
    Off,      // no attr checking at all
    Content,  // content and structure survive; presentation attrs may be dropped
    Exact,    // everything survives; an attr markdown cannot carry is an error
};

struct OtherValue {};
struct OverflowInt {};

using AttrInput = std::variant<std::monostate, bool, long long, std::string,
                               std::vector<long long>, StrMapEntries, OtherValue, OverflowInt>;

void check_type_present(bool present, std::string_view context, const PathStack& path);
const NodeSpec* require_node_spec(const Schema& schema, std::string_view type, const PathStack& path);
const MarkSpec* require_mark_spec(const Schema& schema, std::string_view type, const PathStack& path);
void check_root_type(std::string_view type, const PathStack& path);
void check_node_depth(std::size_t depth, const PathStack& path);
void check_top_level_field(const std::string& name, std::string_view owner_type, const char* kind,
                           bool inline_type, const PathStack& path);
bool node_allows_marks(const NodeSpec& spec);
void check_text_payload(bool present, bool is_string, std::string_view value, const PathStack& path);
void check_raw_carriers(const Node& node, const Schema& schema, const PathStack& path);
// A nullptr result means the attr is unset; callers skip value conversion and checking.
const AttrSpec* check_attr_name(const std::vector<AttrSpec>& specs, const std::string& name, bool is_none,
                                std::string_view owner_type, const char* kind, StrictMode mode,
                                const PathStack& path, bool tag_form = false);
bool attr_reads_string(const AttrSpec& spec);
bool attr_reads_int_list(const AttrSpec& spec);
bool attr_stores_int_list(const std::vector<AttrSpec>& specs, std::string_view name);
bool attr_reads_str_map(const AttrSpec& spec);
bool attr_stores_str_map(const std::vector<AttrSpec>& specs, std::string_view name);
void check_attr_value(const AttrInput& value, const AttrSpec& spec, const PathStack& path);
void check_required_attrs(const AttrList& attrs, const std::vector<AttrSpec>& specs,
                          std::string_view owner_type, const char* kind, const PathStack& path);
void store_attr(AttrList& attrs, std::string&& name, AttrValue&& value, const std::vector<AttrSpec>& specs);
void check_content_field(const NodeSpec& spec, const PathStack& path);
void check_child_content(const Document& document, const NodeSpec& parent, const NodeSpec& child,
                         const Node& child_node, const PathStack& path);
void check_lifted_child_content(const Document& document, const NodeSpec& parent, const NodeSpec& child,
                                const Node& child_node, const PathStack& path);
void check_cell_paragraph_join(const Document& document, const Node& cell, const PathStack& path);
void check_node_marks(const Node& node, const NodeSpec& spec, const PathStack& path);
void check_node_content(const Document& document, std::size_t index, const NodeSpec& spec, const PathStack& path);
void check_representability(const Document& document, const std::vector<std::size_t>& input_parents, bool cjk_friendly);
bool excludes(const ExcludeSet& set, std::string_view type);
void check_mark_set(const std::vector<Mark>& existing, const Mark& mark, const Schema& schema,
                    const PathStack& path);
StrictMode strict_mode_from_string(std::string_view level, const char* arg_name);

}  // namespace marktip
