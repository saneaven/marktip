#pragma once

#include <string>
#include <string_view>
#include <vector>

namespace marktip {

class Document;
class Schema;

// What to do with a link href / image src carrying no scheme at all ("/foo", "#anchor", "./x.png", "").
// PathOnly still rejects protocol-relative references ("//evil.com/x"),
// which have no scheme but do leave the origin.
enum class RelativePolicy { Allow, PathOnly, Reject };

struct UriRule {
    bool restrict_schemes = false;     // false = any scheme is allowed (the default)
    std::vector<std::string> schemes;  // lowercased and sorted, for binary_search
    RelativePolicy relative = RelativePolicy::Allow;
};

// Links and images are governed separately:
// allowing http/mailto for links but only https for images is the common asymmetry.
struct UriPolicy {
    UriRule link;
    UriRule image;
};

// Node types a caller's own ProseMirror dialect refuses even though marktip
// itself knows how to parse and serialize them. Keeping this as a boundary
// policy lets both Markdown and dict inputs report the same located error.
struct NodeTypePolicy {
    std::vector<std::string> rejected;
};

// Applies node-type and URI policies before ordering marks, preserving the input positions in policy errors.
void finalize_document(Document& document, const NodeTypePolicy& node_policy, const UriPolicy& uri_policy);

RelativePolicy relative_policy_from_string(std::string_view value, const char* arg_name);
void add_uri_scheme(UriRule& rule, std::string scheme, const char* arg_name);
void add_rejected_node_type(NodeTypePolicy& policy, std::string type, const Schema& schema, const char* arg_name);

}  // namespace marktip
