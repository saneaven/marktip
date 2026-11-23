#include "normalize.h"

#include "ast.h"
#include "schema.h"

namespace marktip {

void normalize_document(Document& document) {
    if (document.schema().has_declared_marks() || document.schema().has_link_tag()) {
        document.order_marks();
    }
}

void normalize_inherited_attrs(Document& document) {
    // Inherited link attrs can change the link's form and its mark order.
    if (document.schema().has_link_tag()) {
        document.order_marks();
    }
}

}  // namespace marktip
