"""A consumer may close marktip's node set at either write boundary."""

import pytest

import marktip as tm


HTML_NODES = ("htmlBlock", "htmlInline")


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def html_document():
    return doc(
        {"type": "htmlBlock", "attrs": {"html": "<div>x</div>"}},
        {
            "type": "paragraph",
            "content": [{"type": "htmlInline", "attrs": {"html": "<u>y</u>"}}],
        },
    )


@pytest.mark.parametrize(
    "ast, path",
    [
        (html_document(), "content[0]"),
        (
            doc(
                {
                    "type": "paragraph",
                    "content": [{"type": "htmlInline", "attrs": {"html": "<u>x</u>"}}],
                }
            ),
            "content[0].content[0]",
        ),
    ],
)
def test_from_dict_rejects_configured_node_types_with_a_path(ast, path):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, reject_node_types=HTML_NODES)

    err = excinfo.value
    assert err.code == "disallowed_node_type"
    assert err.field == "type"
    assert err.path == path
    assert err.detail == str(err)


@pytest.mark.parametrize(
    "markdown, path",
    [
        ("<div>x</div>", "content[0]"),
        ("a <u>x</u> b", "content[0].content[1]"),
    ],
)
def test_from_markdown_applies_the_same_node_policy(markdown, path):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markdown, reject_node_types=HTML_NODES)

    assert excinfo.value.code == "disallowed_node_type"
    assert excinfo.value.field == "type"
    assert excinfo.value.path == path


def test_html_false_turns_html_into_allowed_literal_text():
    converted = tm.from_markdown("a <u>x</u> b", html=False, reject_node_types=HTML_NODES)
    assert converted.to_markdown(canonical=True) == "a \\<u>x\\</u> b"


def test_no_node_types_are_rejected_by_default():
    assert tm.from_dict(html_document()).to_markdown(canonical=True)
    assert tm.from_markdown("<div>x</div>").to_markdown(canonical=True) == "<div>x</div>"


def test_any_iterable_and_duplicate_entries_are_accepted():
    for rejected in [list(HTML_NODES), set(HTML_NODES), iter(HTML_NODES), HTML_NODES * 2]:
        with pytest.raises(tm.InvalidNodeError, match="htmlBlock"):
            tm.from_dict(html_document(), reject_node_types=rejected)


@pytest.mark.parametrize("bad", ["htmlBlock", b"htmlBlock", 123, ("htmlBlock", 1)])
def test_bad_reject_node_types_option_types_raise_typeerror(bad):
    with pytest.raises(TypeError):
        tm.from_dict(doc(), reject_node_types=bad)
    with pytest.raises(TypeError):
        tm.from_markdown("", reject_node_types=bad)


def test_unknown_rejected_node_type_is_a_valueerror():
    with pytest.raises(ValueError, match="not a known node type"):
        tm.from_dict(doc(), reject_node_types=("callout",))
    with pytest.raises(ValueError, match="not a known node type"):
        tm.from_markdown("", reject_node_types=("callout",))


def test_node_policy_options_are_validated_before_input():
    with pytest.raises(ValueError, match="not a known node type"):
        tm.from_dict({"type": "not-a-doc"}, reject_node_types=("callout",))
