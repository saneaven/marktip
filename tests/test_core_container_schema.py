"""Container overlays activate their core tag family through plain declarations."""

import json

import pytest

import marktip as tm


LIST_TYPES = ("bulletList", "orderedList", "taskList", "listItem", "taskItem")
TABLE_TYPES = ("table", "tableRow", "tableHeader", "tableCell")
CONTAINER_TYPES = ("blockquote", *LIST_TYPES, *TABLE_TYPES)


def text(value):
    return {"type": "text", "text": value}


def test_container_overlays_survive_json_and_schema_cache_keys():
    schema = tm.Schema(core_attrs={
        "blockquote": {"kind": tm.Attr(str, choices=("note", "warning"), default="note")},
        "bulletList": {"id": tm.Attr(str)},
        "orderedList": {"type": tm.Attr(str, choices=("1", "a"), default="1")},
        "listItem": {"depth": tm.Attr(int, default=0)},
        "taskList": {"enabled": tm.Attr(bool, default=False)},
        "taskItem": {"source": tm.Attr(str, uri="link")},
        "table": {"id": tm.Attr(str)},
        "tableRow": {"label": tm.Attr(str)},
        "tableHeader": {"colspan": tm.Attr(int, default=1)},
        "tableCell": {"rowspan": tm.Attr(int, default=1), "colwidth": tm.Attr(tm.IntList)},
    })
    declaration = schema.to_dict()
    assert list(declaration["core_attrs"]["tableCell"]) == ["rowspan", "colwidth"]
    assert declaration["core_attrs"]["tableCell"]["colwidth"]["type"] == "IntList"
    assert declaration["core_attrs"]["tableHeader"]["colspan"]["default"] == 1
    restored = tm.Schema.from_dict(json.loads(json.dumps(declaration)))
    assert restored == schema
    assert hash(restored) == hash(schema)
    assert restored.to_dict() == declaration
    assert {schema: "cached"}[restored] == "cached"


@pytest.mark.parametrize("owner", CONTAINER_TYPES)
def test_each_container_owner_accepts_an_optional_overlay_without_adding_other_declarations(owner):
    attrs = {owner: {"data-label": tm.Attr(str)}}
    schema = tm.Schema(core_attrs=attrs)
    assert schema.core_attrs == attrs
    assert list(schema.to_dict()["core_attrs"]) == [owner]


@pytest.mark.parametrize("owner", CONTAINER_TYPES)
def test_container_overlays_cannot_be_required(owner):
    with pytest.raises(ValueError):
        tm.Schema(core_attrs={owner: {"id": tm.Attr(str, required=True)}})


@pytest.mark.parametrize("owner, name", (
    ("bulletList", "tight"),
    ("orderedList", "tight"),
    ("orderedList", "start"),
    ("taskList", "tight"),
    ("taskItem", "checked"),
    ("table", "colCount"),
    ("tableHeader", "align"),
    ("tableCell", "align"),
))
def test_markdown_carried_container_attrs_cannot_be_redeclared(owner, name):
    with pytest.raises(ValueError):
        tm.Schema(core_attrs={owner: {name: tm.Attr(str)}})


@pytest.mark.parametrize("owner", ("tableHeader", "tableCell"))
def test_cell_span_rules_can_be_replaced_and_column_widths_have_a_declared_type(owner):
    attrs = {"colspan": tm.Attr(int, default=1), "rowspan": tm.Attr(int, default=1),
             "colwidth": tm.Attr(tm.IntList, choices=([100], [100, 200]), default=[100])}
    schema = tm.Schema(core_attrs={owner: attrs})
    assert schema.core_attrs[owner] == attrs
    restored = tm.Schema.from_dict(json.loads(json.dumps(schema.to_dict())))
    assert restored == schema
    assert hash(restored) == hash(schema)


def test_extend_merges_container_attrs_without_changing_the_base():
    base = tm.Schema(core_attrs={"blockquote": {"kind": tm.Attr(str)}, "tableCell": {"colspan": tm.Attr(int)}})
    before = base.to_dict()
    extended = base.extend(core_attrs={"tableCell": {"colwidth": tm.Attr(tm.IntList)},
                                       "listItem": {"id": tm.Attr(str)}})
    expected = tm.Schema(core_attrs={
        "blockquote": {"kind": tm.Attr(str)},
        "tableCell": {"colspan": tm.Attr(int), "colwidth": tm.Attr(tm.IntList)},
        "listItem": {"id": tm.Attr(str)},
    })
    assert extended == expected
    assert hash(extended) == hash(expected)
    assert base.to_dict() == before
    with pytest.raises(ValueError):
        base.extend(core_attrs={"tableCell": {"colspan": tm.Attr(int)}})


@pytest.mark.parametrize("owner", LIST_TYPES)
@pytest.mark.parametrize("html", (True, False))
def test_any_list_owner_activates_ul_ol_and_li_tags(owner, html):
    schema = tm.Schema(core_attrs={owner: {}})
    source = "<ul>\n<li>\nbullet\n</li>\n</ul>\n\n<ol start=3>\n<li>\nordered\n</li>\n</ol>"
    blocks = tm.from_markdown(source, schema=schema, html=html).to_dict()["content"]
    assert [block["type"] for block in blocks] == ["bulletList", "orderedList"]
    for block, value in zip(blocks, ("bullet", "ordered")):
        assert block["content"][0]["type"] == "listItem"
        assert block["content"][0]["content"] == [{"type": "paragraph", "content": [text(value)]}]
    assert blocks[1]["attrs"]["start"] == 3


@pytest.mark.parametrize("owner", LIST_TYPES)
def test_any_list_owner_activates_checked_items_and_task_list_normalization(owner):
    schema = tm.Schema(core_attrs={owner: {}})
    source = '<ul>\n<li checked="false">\ntask\n</li>\n<li>\nplain\n</li>\n</ul>'
    block = tm.from_markdown(source, schema=schema).to_dict()["content"][0]
    assert block["type"] == "taskList"
    assert [item["type"] for item in block["content"]] == ["taskItem", "taskItem"]
    assert [item["attrs"]["checked"] for item in block["content"]] == [False, False]


@pytest.mark.parametrize("owner", TABLE_TYPES)
@pytest.mark.parametrize("html", (True, False))
def test_any_table_owner_activates_table_tr_th_and_td_tags(owner, html):
    schema = tm.Schema(core_attrs={owner: {}})
    source = '<table>\n<tr>\n<th>\nheader\n</th>\n</tr>\n<tr>\n<td align="right">\nvalue\n</td>\n</tr>\n</table>'
    block = tm.from_markdown(source, schema=schema, html=html).to_dict()["content"][0]
    assert block["type"] == "table"
    assert [row["type"] for row in block["content"]] == ["tableRow", "tableRow"]
    header, cell = (row["content"][0] for row in block["content"])
    assert (header["type"], cell["type"]) == ("tableHeader", "tableCell")
    assert header["content"] == [{"type": "paragraph", "content": [text("header")]}]
    assert cell["content"] == [{"type": "paragraph", "content": [text("value")]}]
    assert cell["attrs"]["align"] == "right"


@pytest.mark.parametrize("source, unrelated", (
    ("<blockquote>\nx\n</blockquote>", "table"),
    ("<ul>\n<li>\nx\n</li>\n</ul>", "blockquote"),
    ("<table>\n<tr>\n<td>\nx\n</td>\n</tr>\n</table>", "bulletList"),
))
@pytest.mark.parametrize("html", (True, False))
def test_inactive_container_tags_keep_the_existing_raw_html_behavior(source, unrelated, html):
    expected = tm.from_markdown(source, html=html).to_dict()
    assert tm.from_markdown(source, schema=tm.Schema(core_attrs={unrelated: {}}), html=html).to_dict() == expected


@pytest.mark.parametrize("owner", ("bulletList", "orderedList", "taskList", "table"))
def test_empty_lists_and_tables_keep_the_existing_written_form(owner):
    ast = {"type": "doc", "content": [{"type": owner}]}
    baseline = tm.from_dict(ast, strict="exact").to_markdown()
    assert tm.from_dict(ast, schema=tm.Schema(core_attrs={owner: {}}), strict="exact").to_markdown() == baseline
