#include "entities.h"

// md4c's named-entity table,
// used to resolve references inside a link href / image src before the URI policy inspects it.
// entity.h is not part of md4c's public API and has no extern "C" guard of its own;
// the coupling is recorded in third_party/md4c/upstream_metadata/README.md.
extern "C" {
#include "entity.h"
}

#include <algorithm>

namespace marktip {
namespace {

bool is_scheme_alpha(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}

void append_utf8(unsigned codepoint, std::string& out) {
    if (codepoint < 0x80) {
        out.push_back(static_cast<char>(codepoint));
    } else if (codepoint < 0x800) {
        out.push_back(static_cast<char>(0xC0 | (codepoint >> 6)));
        out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    } else if (codepoint < 0x10000) {
        out.push_back(static_cast<char>(0xE0 | (codepoint >> 12)));
        out.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    } else {
        out.push_back(static_cast<char>(0xF0 | (codepoint >> 18)));
        out.push_back(static_cast<char>(0x80 | ((codepoint >> 12) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
    }
}

// `body` is what sits between '&' and ';', starting with '#'.
bool append_numeric_entity(std::string_view body, std::string& out) {
    std::size_t i = 1;
    unsigned base = 10;
    if (i < body.size() && (body[i] == 'x' || body[i] == 'X')) {
        base = 16;
        ++i;
    }
    if (i >= body.size()) {
        return false;
    }

    unsigned long long value = 0;
    bool overflow = false;
    for (; i < body.size(); ++i) {
        char c = body[i];
        unsigned digit;
        if (c >= '0' && c <= '9') {
            digit = static_cast<unsigned>(c - '0');
        } else if (base == 16 && c >= 'a' && c <= 'f') {
            digit = static_cast<unsigned>(c - 'a') + 10;
        } else if (base == 16 && c >= 'A' && c <= 'F') {
            digit = static_cast<unsigned>(c - 'A') + 10;
        } else {
            return false;
        }
        if (!overflow) {
            value = value * base + digit;
            overflow = value > 0x10FFFF;
        }
    }

    // Same substitution the HTML spec makes:
    // NUL, surrogates and out-of-range values render as U+FFFD rather than as the raw codepoint.
    unsigned codepoint = static_cast<unsigned>(value);
    if (overflow || codepoint == 0 || (codepoint >= 0xD800 && codepoint <= 0xDFFF)) {
        codepoint = 0xFFFD;
    }
    append_utf8(codepoint, out);
    return true;
}

// `entity` includes the '&' and the ';': that is md4c's table key format ("&amp;").
bool append_named_entity(std::string_view entity, std::string& out) {
    const ENTITY* found = entity_lookup(entity.data(), entity.size());
    if (found == nullptr) {
        return false;
    }
    append_utf8(found->codepoints[0], out);
    if (found->codepoints[1] != 0) {
        append_utf8(found->codepoints[1], out);
    }
    return true;
}

// Offset of the ';' closing an entity that starts at value[0] == '&', or npos.
//
// The terminator is found by consuming the characters an entity may contain,
// rather than by searching ahead for a ';':
// a query string full of separators and no semicolon at all ("?a=1&b=2&c=3...")
// would otherwise rescan the tail for every '&'.
// Numeric references follow MD4C's limits of seven decimal or six hexadecimal digits,
// so a renderer leaves a longer reference literal rather than turning it into a scheme character.
std::size_t entity_semicolon(std::string_view value) {
    auto is_digit = [](char c) { return c >= '0' && c <= '9'; };
    auto is_hex = [&](char c) { return is_digit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'); };

    std::size_t i = 1;
    if (i < value.size() && value[i] == '#') {
        ++i;
        if (i < value.size() && (value[i] == 'x' || value[i] == 'X')) {
            ++i;
            std::size_t stop = std::min(value.size(), i + 6);
            while (i < stop && is_hex(value[i])) {
                ++i;
            }
        } else {
            std::size_t stop = std::min(value.size(), i + 7);
            while (i < stop && is_digit(value[i])) {
                ++i;
            }
        }
    } else {
        // Every HTML5 named reference is ASCII alphanumeric;
        // the longest, "CounterClockwiseContourIntegral", is 31 characters.
        constexpr std::size_t kMaxNamedEntity = 32;
        std::size_t stop = std::min(value.size(), 1 + kMaxNamedEntity);
        while (i < stop && (is_digit(value[i]) || is_scheme_alpha(value[i]))) {
            ++i;
        }
    }

    if (i > 1 && i < value.size() && value[i] == ';') {
        return i;
    }
    return std::string_view::npos;
}

}  // namespace

// Resolves entity references the way a renderer will.
//
// The policy has to run on the decoded form.
// MD4C hands entity substrings through verbatim,
// so "&#106;avascript:alert(1)" is what actually reaches the AST —
// and it is still "javascript:alert(1)" the moment a consumer drops it into an HTML attribute.
// An allowlist that this walks straight through is not an allowlist.
// Single pass, like a browser: "&amp;#106;" yields "&#106;" and stops there.
//
// Core Markdown URI attrs keep their original text and use this decoded form only for policy checks.
// Declared tag attrs store the decoded value.
std::string decode_entities(std::string_view value) {
    std::string out;
    out.reserve(value.size());
    std::size_t i = 0;
    while (i < value.size()) {
        std::size_t end = std::string_view::npos;
        if (value[i] == '&') {
            std::size_t offset = entity_semicolon(value.substr(i));
            if (offset != std::string_view::npos) {
                end = i + offset;
            }
        }
        if (end == std::string_view::npos) {
            out.push_back(value[i]);
            ++i;
            continue;
        }

        std::string_view body = value.substr(i + 1, end - i - 1);
        bool decoded = false;
        if (body.empty()) {
            decoded = false;
        } else if (body.front() == '#') {
            decoded = append_numeric_entity(body, out);
        } else {
            decoded = append_named_entity(value.substr(i, end - i + 1), out);
        }

        if (decoded) {
            i = end + 1;
        } else {
            out.push_back(value[i]);
            ++i;
        }
    }
    return out;
}


}  // namespace marktip
