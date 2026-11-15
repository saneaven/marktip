import pytest

import marktip as tm


HTML = (True, False)


def doc(*children):
    return {"type": "doc", "content": list(children)}


def node(type_, *children, attrs=None):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    if children:
        result["content"] = list(children)
    return result


def text(value):
    return {"type": "text", "text": value}


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("type_", ("embed", "lead"))
def test_a_lone_block_atom_or_textblock_cell_keeps_its_pipe_table(html, type_):
    selected = tm.Schema(
        nodes=[tm.NodeSpec("embed", "block"), tm.NodeSpec("lead", "block", content="inline*")],
        core_attrs=tm.TABLE_SPANS,
    )
    child = node("embed") if type_ == "embed" else node("lead", text("Lead"))
    ast = doc(node("table", node("tableRow", node("tableHeader", child)), attrs={"colCount": 1}))
    source = tm.from_dict(ast, schema=selected, strict="exact")
    written = source.to_markdown(canonical=True)
    assert written == f"| {'<embed/>' if type_ == 'embed' else '<lead>Lead</lead>'} |\n| --- |"
    assert tm.from_markdown(written, schema=selected, html=html).to_dict() == source.to_dict()


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("aligned", (False, True))
def test_heading_cells_use_pipe_form_only_when_the_heading_is_written_as_a_textblock_tag(html, aligned):
    selected = tm.Schema(core_attrs={**tm.TABLE_SPANS, **tm.TEXT_ALIGN})
    attrs = {"level": 2, **({"textAlign": "right"} if aligned else {})}
    heading = node("heading", text("Title"), attrs=attrs)
    ast = doc(node("table", node("tableRow", node("tableHeader", heading)), attrs={"colCount": 1}))
    source = tm.from_dict(ast, schema=selected, strict="exact")
    written = source.to_markdown(canonical=True)
    if aligned:
        assert written == '| <h2 textAlign="right">Title</h2> |\n| --- |'
    else:
        assert written.startswith("<table")
        assert "## Title" in written
    parsed = tm.from_markdown(written, schema=selected, html=html)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown(canonical=True) == written


