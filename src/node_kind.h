#pragma once

#include <cstring>
#include <string_view>

namespace marktip {

enum class NodeKind {
    Text, CodeText, HardBreak, Paragraph, EmptyParagraph, Heading, OrderedList, List, TaskItem, Image, Table,
    TableCell, CodeBlock, ParagraphContainer, Container, Other, Removed
};

inline NodeKind node_kind(std::string_view type) {
    const char* name = type.data();
    switch (type.size()) {
    case 3:
        if (std::memcmp(name, "doc", 3) == 0) return NodeKind::Container;
        break;
    case 4:
        if (std::memcmp(name, "text", 4) == 0) return NodeKind::Text;
        break;
    case 5:
        if (std::memcmp(name, "table", 5) == 0) return NodeKind::Table;
        if (std::memcmp(name, "image", 5) == 0) return NodeKind::Image;
        break;
    case 7:
        if (std::memcmp(name, "heading", 7) == 0) return NodeKind::Heading;
        break;
    case 8:
        if (std::memcmp(name, "taskItem", 8) == 0) return NodeKind::TaskItem;
        if (std::memcmp(name, "listItem", 8) == 0) return NodeKind::ParagraphContainer;
        if (std::memcmp(name, "tableRow", 8) == 0) return NodeKind::Container;
        if (std::memcmp(name, "taskList", 8) == 0) return NodeKind::List;
        break;
    case 9:
        if (std::memcmp(name, "paragraph", 9) == 0) return NodeKind::Paragraph;
        if (std::memcmp(name, "hardBreak", 9) == 0) return NodeKind::HardBreak;
        if (std::memcmp(name, "codeBlock", 9) == 0) return NodeKind::CodeBlock;
        if (std::memcmp(name, "tableCell", 9) == 0) return NodeKind::TableCell;
        break;
    case 10:
        if (std::memcmp(name, "blockquote", 10) == 0) return NodeKind::ParagraphContainer;
        if (std::memcmp(name, "bulletList", 10) == 0) return NodeKind::List;
        break;
    case 11:
        if (std::memcmp(name, "orderedList", 11) == 0) return NodeKind::OrderedList;
        if (std::memcmp(name, "tableHeader", 11) == 0) return NodeKind::TableCell;
        break;
    }
    return NodeKind::Other;
}

}  // namespace marktip
