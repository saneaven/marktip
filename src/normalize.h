#pragma once

namespace marktip {

class Document;

void normalize_document(Document& document);
void normalize_inherited_attrs(Document& document);

}  // namespace marktip
