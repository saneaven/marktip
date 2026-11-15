#pragma once

#include "input.h"
#include "parser.h"
#include "policy.h"
#include "validate.h"

namespace marktip::wasm {

struct ConversionOptions {
    UriPolicy uri;
    NodeTypePolicy nodes;
    StrictMode strict = StrictMode::Off;
    ParseOptions parser;
};

ConversionOptions read_options(JsonInput::Value value, const Schema& schema, bool from_dict);

}  // namespace marktip::wasm
