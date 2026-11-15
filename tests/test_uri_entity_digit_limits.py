import pytest

import marktip as tm


def uri_ast(kind, value):
    if kind == "link":
        child = {"type": "text", "text": "x", "marks": [{"type": "link", "attrs": {"href": value}}]}
    else:
        child = {"type": "image", "attrs": {"src": value, "alt": "x"}}
    return {"type": "doc", "content": [{"type": "paragraph", "content": [child]}]}


@pytest.mark.parametrize("kind, field", [("link", "href"), ("image", "src")])
@pytest.mark.parametrize("boundary", ["dict", "markdown"])
@pytest.mark.parametrize("reference", ["&#0000000058;", "&#x000003a;"])
def test_overlong_numeric_uri_references_are_literal_relative_destinations(kind, field, boundary, reference):
    value = "https" + reference + "//example.com"
    options = {kind + "_schemes": ("https",), kind + "_relative": "reject"}
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        if boundary == "dict":
            tm.from_dict(uri_ast(kind, value), **options)
        else:
            tm.from_markdown(("!" if kind == "image" else "") + "[x](" + value + ")", **options)
    assert (excinfo.value.code, excinfo.value.field) == ("disallowed_relative_url", field)


@pytest.mark.parametrize("kind", ["link", "image"])
@pytest.mark.parametrize("reference", ["&#0000058;", "&#x00003a;"])
def test_numeric_uri_references_at_md4cs_digit_limit_are_decoded(kind, reference):
    value = "https" + reference + "//example.com"
    options = {kind + "_schemes": ("https",), kind + "_relative": "reject"}
    assert tm.from_dict(uri_ast(kind, value), **options).to_dict() == uri_ast(kind, value)
