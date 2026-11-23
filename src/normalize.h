#pragma once

#include "inherit.h"

namespace marktip {

class Document;

void normalize_document(Document& document, bool cjk_friendly, InputAttrKeys* present = nullptr);
void normalize_inherited_attrs(Document& document);

}  // namespace marktip
