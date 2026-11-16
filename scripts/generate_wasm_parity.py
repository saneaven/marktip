"""Write native document and schema results for the wasm parity test."""

import argparse
import json
from pathlib import Path
import sys

import marktip as tm


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from spec_examples import EDGE_DOCUMENTS, EXAMPLES, block_schema, editor_dict


def snapshot(document):
    return {
        "dict": document.to_dict(),
        "dump": document.dump(),
        "markdown": document.to_markdown(),
        "canonical": document.to_markdown(canonical=True),
    }


def pinned_schema():
    return tm.Schema(marks=[
        tm.MarkSpec("note", attrs={
            "label": tm.Attr(str, choices=("red", "blue"), default="red"),
            "count": tm.Attr(int, default=-2),
            "enabled": tm.Attr(bool, default=True),
            "widths": tm.Attr(tm.IntList, default=[100, 200]),
        }, excludes=("bold",)),
        tm.MarkSpec("exclusive", excludes="_"),
        tm.MarkSpec("plain"),
    ])


OPTION_NAMES = {
    "cjk_friendly": "cjkFriendly", "keep_source": "keepSource",
    "link_schemes": "linkSchemes", "image_schemes": "imageSchemes",
    "link_relative": "linkRelative", "image_relative": "imageRelative",
    "reject_node_types": "rejectNodeTypes",
}


def js_options(options):
    return {OPTION_NAMES.get(key, key): value for key, value in options.items()}


def error_result(call):
    try:
        call()
    except tm.MarktipError as error:
        result = {
            "name": type(error).__name__, "message": str(error),
            "code": error.code, "path": error.path, "detail": error.detail,
        }
        for key in ("field", "type", "kind"):
            if hasattr(error, key):
                result[key] = getattr(error, key)
        return result
    raise AssertionError("an error fixture succeeded")


def declaration_error_result(call):
    try:
        call()
    except (TypeError, ValueError) as error:
        return {"name": "TypeError" if isinstance(error, TypeError) else "RangeError", "message": str(error)}
    raise AssertionError("a declaration error fixture succeeded")


def schema_results(payload):
    mark_names = ("UNDERLINE", "HIGHLIGHT", "SUBSCRIPT", "SUPERSCRIPT", "TEXT_STYLE")
    node_names = ("MENTION", "INLINE_MATH", "BLOCK_MATH")
    core_names = ("TEXT_ALIGN", "LINK_ATTRS", "IMAGE_SIZE", "TABLE_SPANS")
    payload["presets"] = []
    for name in mark_names:
        value = tm.Schema(marks=[getattr(tm, name)]).to_dict()["marks"][0]
        payload["presets"].append({"name": name, "expected": value})
    for name in node_names:
        value = tm.Schema(nodes=[getattr(tm, name)]).to_dict()["nodes"][0]
        payload["presets"].append({"name": name, "expected": value})
    payload["presets"].append({"name": "DETAILS", "expected": tm.Schema(nodes=tm.DETAILS).to_dict()["nodes"]})
    for name in core_names:
        value = tm.Schema(core_attrs=getattr(tm, name)).to_dict()["core_attrs"]
        payload["presets"].append({"name": name, "expected": value})

    payload["presetFunctions"] = []
    factory_cases = [
        ("textStyle", {}, {}),
        ("textStyle", {"background_color": False, "font_size": False},
         {"backgroundColor": False, "fontSize": False}),
        ("textStyle", {"background_color": False, "color": False, "font_family": False,
                       "font_size": False, "line_height": False},
         {"backgroundColor": False, "color": False, "fontFamily": False, "fontSize": False, "lineHeight": False}),
        ("textStyle", {"merge_nested_span_styles": False}, {"mergeNestedSpanStyles": False}),
        ("textAlign", {}, {}),
        ("textAlign", {"types": ("paragraph",), "alignments": ("left", "right"), "default_alignment": "right"},
         {"types": ["paragraph"], "alignments": ["left", "right"], "defaultAlignment": "right"}),
        ("textAlign", {"types": ("heading", "paragraph"), "alignments": ("center",), "default_alignment": None},
         {"types": ["heading", "paragraph"], "alignments": ["center"], "defaultAlignment": None}),
        ("linkAttrs", {}, {}),
        ("linkAttrs", {"target": "_self", "rel": "nofollow", "class_": "reference"},
         {"target": "_self", "rel": "nofollow", "class": "reference"}),
        ("linkAttrs", {"target": None, "rel": None, "class_": None},
         {"target": None, "rel": None, "class": None}),
    ]
    factories = {"textStyle": tm.text_style, "textAlign": tm.text_align, "linkAttrs": tm.link_attrs}
    for index, (name, python_options, options) in enumerate(factory_cases):
        value = factories[name](**python_options)
        if name == "textStyle":
            expected = tm.Schema(marks=[value]).to_dict()["marks"][0]
        else:
            expected = tm.Schema(core_attrs=value).to_dict()["core_attrs"]
        payload["presetFunctions"].append({"id": f"{name}-{index}", "function": name,
                                           "options": options, "expected": expected})

    all_presets = tm.Schema(
        marks=[getattr(tm, name) for name in mark_names],
        nodes=[tm.MENTION, *tm.DETAILS, tm.INLINE_MATH, tm.BLOCK_MATH],
        core_attrs={**tm.TEXT_ALIGN, **tm.LINK_ATTRS, **tm.IMAGE_SIZE, **tm.TABLE_SPANS},
    )
    declarations = [
        ("empty", {"marks": []}),
        ("defaults", {"marks": [{"name": "note", "attrs": {"tone": {"type": "str"}}}],
                      "nodes": [{"name": "mention", "kind": "inline", "attrs": {"id": {"type": "str"}}}]}),
        ("all-attr-types", pinned_schema().to_dict()),
        ("str-map", payload["schemas"]["str-map"]),
        ("all-presets", all_presets.to_dict()),
        ("block-image", {"marks": [], "block_image": True}),
        ("empty-core-owner", {"marks": [], "core_attrs": {"paragraph": {}}}),
    ]
    payload["schemaCases"] = []
    for name, declaration in declarations:
        schema = tm.Schema.from_dict(declaration)
        payload["schemaCases"].append({
            "id": name, "declaration": declaration, "expected": schema.to_dict(),
            "fingerprint": tm.from_markdown("", schema=schema).dump()["schema"],
        })

    base = tm.Schema(marks=[tm.UNDERLINE], nodes=[tm.MENTION], core_attrs=tm.LINK_ATTRS, block_image=True)
    additions = tm.Schema(marks=[tm.HIGHLIGHT], nodes=[tm.BLOCK_MATH], core_attrs=tm.IMAGE_SIZE)
    same_owner = tm.Schema(core_attrs={"link": {"download": tm.Attr(bool, default=False)}})
    extension_cases = [
        ("inherit-block-image", base, additions, None),
        ("replace-block-image", base, same_owner, False),
        ("enable-block-image", tm.Schema(), tm.Schema(), True),
        ("no-additions", base, tm.Schema(), None),
    ]
    payload["extensions"] = []
    for name, original, extra, block_image in extension_cases:
        extended = original.extend(marks=extra.marks, nodes=extra.nodes, core_attrs=extra.core_attrs,
                                   block_image=block_image)
        options = extra.to_dict()
        if block_image is not None:
            options["block_image"] = block_image
        payload["extensions"].append({
            "id": name, "base": original.to_dict(), "addition": options, "expected": extended.to_dict(),
            "fingerprint": tm.from_markdown("", schema=extended).dump()["schema"],
        })

    invalid_declarations = [
        ("duplicate-mark", {"marks": [{"name": "note"}, {"name": "note", "tag": "other"}]}),
        ("reserved-type", {"marks": [{"name": "paragraph", "tag": "custom"}]}),
        ("bad-tag", {"marks": [{"name": "note", "tag": "bad tag"}]}),
        ("bad-exclusion", {"marks": [{"name": "note", "excludes": ["missing"]}]}),
        ("bad-attr-type", {"marks": [{"name": "note", "attrs": {"tone": {"type": "float"}}}]}),
        ("bad-default", {"marks": [{"name": "note", "attrs": {"tone": {"type": "int", "default": "x"}}}]}),
        ("bad-required-type", {"marks": [{"name": "note", "attrs": {"tone": {"type": "str", "required": 1}}}]}),
        ("bad-node-kind", {"marks": [], "nodes": [{"name": "custom", "kind": "other"}]}),
        ("bad-content", {"marks": [], "nodes": [{"name": "custom", "kind": "block", "content": "missing+"}]}),
        ("unknown-core-owner", {"marks": [], "core_attrs": {"missing": {"tone": {"type": "str"}}}}),
        ("str-map-prefix-conflict", {"marks": [{"name": "status", "attrs": {
            "data": {"type": "StrMap"}, "data-hp": {"type": "str"},
        }}]}),
    ]
    payload["schemaErrors"] = [
        {"id": name, "declaration": declaration,
         "expected": declaration_error_result(lambda: tm.Schema.from_dict(declaration))}
        for name, declaration in invalid_declarations
    ]
    payload["duplicateCoreAttr"] = {
        "base": base.to_dict(), "addition": tm.Schema(core_attrs=tm.LINK_ATTRS).to_dict(),
        "expected": declaration_error_result(lambda: base.extend(core_attrs=tm.LINK_ATTRS)),
    }


def generate():
    partial_schema = tm.Schema(
        marks=[tm.UNDERLINE],
        nodes=[
            tm.NodeSpec("callout", "block", content="block+", attrs={"tone": tm.Attr(str)}),
            tm.NodeSpec("summary", "block", content="inline*"),
            tm.NodeSpec("ruby", "inline", content="inline*"),
        ],
    )
    schemas = {
        "default": None,
        "declared": block_schema(),
        "partial": partial_schema,
        "pinned": pinned_schema(),
        "empty": tm.Schema(),
        "overlays": tm.Schema(core_attrs={**tm.TEXT_ALIGN, **tm.LINK_ATTRS, **tm.IMAGE_SIZE, **tm.TABLE_SPANS}),
        "styles": tm.Schema(marks=[tm.TEXT_STYLE, tm.UNDERLINE]),
        "styles-unmerged": tm.Schema(marks=[tm.text_style(merge_nested_span_styles=False)]),
        "str-map": tm.Schema(
            marks=[tm.MarkSpec("status", tag="custom-span", attrs={"data": tm.Attr(tm.StrMap)})],
            nodes=[tm.NodeSpec("customDiv", "block", content="block+", tag="custom-div", attrs={
                "class": tm.Attr(str), "data": tm.Attr(tm.StrMap),
            })],
            core_attrs={"paragraph": {"aria": tm.Attr(tm.StrMap)}},
        ),
    }
    payload = {
        "version": tm.__version__,
        "schemas": {name: None if schema is None else schema.to_dict() for name, schema in schemas.items()},
        "documents": [], "errors": [], "partial": [], "fingerprints": [],
    }

    def add_document(name, markdown, schema_name, **options):
        schema = schemas[schema_name]
        document = tm.from_markdown(markdown, schema=schema, **options)
        loaded = tm.load(document.dump(), schema=schema)
        editor_input = editor_dict(document.to_dict())
        edited = tm.from_dict(editor_input, schema=schema, base=loaded)
        payload["documents"].append({
            "id": name, "markdown": markdown, "schema": schema_name, "options": js_options(options),
            "expected": snapshot(document), "loadedDump": loaded.dump(),
            "editorInput": editor_input, "editorExpected": snapshot(edited),
        })

    examples = [(example.id, example.values[0]) for example in EXAMPLES]
    examples += [(f"edge-{index}", markdown) for index, markdown in enumerate(EDGE_DOCUMENTS)]
    for schema_name in ("default", "declared"):
        for name, markdown in examples:
            add_document(f"{schema_name}/{name}", markdown, schema_name)
    add_document("declared/tag-forms", '<callout tone="note">\n\nbody\n\n</callout>\n\n'
                 '<embed label="video" enabled="true"/>\n', "declared")
    add_document("options/cjk", "**《제목》**a", "default", cjk_friendly=True)
    add_document("options/html", "a <span>x</span> b", "default", html=False)
    add_document("options/no-source", "\nTitle\n=====\n\n* first\n", "default", keep_source=False)
    nested_spans = ('<span color="red">a <span fontSize="12px">b <u>c <span lineHeight="2">d</span></u></span> '
                    '<span color="blue">e</span></span>\n')
    add_document("styles/nested-spans", nested_spans, "styles")
    add_document("styles/nested-spans-unmerged", '<span color="red">a <span fontSize="12px">b</span></span>\n',
                 "styles-unmerged")
    add_document("text/leading-bom", "\ufeffHello\n", "default")
    add_document("text/control-characters", "before\u0001\u0008\u000c\u001fafter\n", "default")
    add_document("overlays/tag-forms", '<p textAlign="center">Aligned</p>\n\n'
                 '<a href="/docs" target="_self">Docs</a> '
                 '<img src="logo.png" width="100" height="80"/>', "overlays")
    add_document("str-map/mark", '<custom-span data-hp=\'30\' data-name="리안" data-MixedCase="" '
                 'data-2nd="&amp;&quot;&lt;&gt;&#124;&#96;&#10;">x</custom-span>', "str-map")
    add_document("str-map/node", '<custom-div class="game.status" data-hp="30" data-name="리안">\n\n'
                 'x\n\n</custom-div>', "str-map")
    add_document("str-map/core", '<p aria-label="status" aria-description="리안">x</p>', "str-map")
    add_document("inline-container/declared-mark", "<u>a <ruby>x</ruby> b</u>", "partial")
    add_document("inline-container/delimiter-mark", "**a <ruby>x</ruby> b**", "partial")
    add_document("inline-container/own-and-child-marks", "<u><ruby><u>x</u></ruby></u>", "partial")

    source = '<callout tone="note">\n\n<summary><ruby><u>body</u></ruby></summary>\n\n</callout>'
    for length in (0, 1, 8, 20, 22, 31, 37, 40, len(source) - 4, len(source)):
        markdown = source[:length]
        document = tm.from_markdown(markdown, schema=partial_schema, partial=True)
        payload["partial"].append({
            "id": f"prefix-{length}", "markdown": markdown, "schema": "partial",
            "options": {"partial": True}, "expected": snapshot(document),
        })
    document = tm.from_markdown("<callout>\n\nbody", schema=partial_schema, partial=True, keep_source=False)
    payload["partial"].append({
        "id": "no-source", "markdown": "<callout>\n\nbody", "schema": "partial",
        "options": {"partial": True, "keepSource": False}, "expected": snapshot(document),
    })

    for schema_name in ("default", "empty", "declared", "pinned", "overlays", "str-map"):
        fingerprint = tm.from_markdown("", schema=schemas[schema_name]).dump()["schema"]
        payload["fingerprints"].append({"schema": schema_name, "expected": fingerprint})
    assert payload["fingerprints"][0]["expected"] == "d4657f55662f817f"
    pinned = next(item for item in payload["fingerprints"] if item["schema"] == "pinned")
    assert pinned["expected"] == "6a72285e381606f4"

    errors = [
        ("markdown-max-depth", "fromMarkdown", ">" * 50000 + " x", "default", {}),
        ("unknown-node", "fromDict", {"type": "doc", "content": [{"type": "unregistered"}]}, "default", {}),
        ("unknown-mark", "fromDict", {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "x", "marks": [{"type": "unregistered"}]},
        ]}]}, "default", {}),
        ("missing-type", "fromDict", {"content": []}, "default", {}),
        ("wrong-attrs", "fromDict", {"type": "doc", "content": [{"type": "paragraph", "attrs": []}]}, "default", {}),
        ("strict-null-marks", "fromDict", {"type": "doc", "content": [{"type": "paragraph", "marks": None}]},
         "default", {"strict": "exact"}),
        ("integer-overflow", "fromDict", {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 10**20}}]},
         "default", {"strict": "exact"}),
        ("fractional-number", "fromDict", {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 1.5}}]},
         "default", {"strict": "exact"}),
        ("exponent-number", "fromDict", {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 1e21}}]},
         "default", {"strict": "exact"}),
        ("unmatched-tag", "fromMarkdown", "</callout>", "declared", {}),
        ("inline-container/declared-mark-closes-inside", "fromMarkdown", "<u>a <ruby>x</u> y</ruby>",
         "partial", {}),
        ("inline-container/declared-mark-closes-outside", "fromMarkdown", "<ruby>a <u>b</ruby> c</u>",
         "partial", {}),
        ("inline-container/delimiter-mark-closes-inside", "fromMarkdown", "**a <ruby>x** y</ruby>",
         "partial", {}),
        ("inline-container/delimiter-mark-closes-outside", "fromMarkdown", "<ruby>a **b</ruby> c**",
         "partial", {}),
        ("bad-tag-attr", "fromMarkdown", '<callout unknown="value">\n\n</callout>', "declared", {}),
        ("relative-link", "fromMarkdown", "[link](/path)", "default", {"link_relative": "reject"}),
        ("link-schemes", "fromMarkdown", "[link](http://example.test/page)",
         "default", {"link_schemes": ["https"]}),
        ("image-schemes", "fromMarkdown", "![image](http://example.test/image.png)",
         "default", {"image_schemes": ["https"]}),
        ("relative-image", "fromMarkdown", "![image](/image.png)", "default", {"image_relative": "reject"}),
        ("rejected-node", "fromMarkdown", "# Title", "default", {"reject_node_types": ["heading"]}),
        ("str-map-valueless-entry", "fromMarkdown", '<custom-span data-hp>x</custom-span>', "str-map", {}),
        ("str-map-repeated-entry", "fromMarkdown", '<custom-span data-hp="30" data-hp="20">x</custom-span>',
         "str-map", {}),
        ("str-map-bare-attr", "fromMarkdown", '<custom-span data="hp=30">x</custom-span>', "str-map", {}),
        ("str-map-empty-key", "fromMarkdown", '<custom-span data-="30">x</custom-span>', "str-map", {}),
        ("str-map-unknown-prefix", "fromMarkdown", '<custom-span aria-label="x">x</custom-span>', "str-map", {}),
    ]
    for strict in ("content", "exact"):
        for name, value in (("non-dict", "label"), ("non-string-value", {"label": 1}),
                            ("empty-key", {"": "x"}), ("invalid-key", {"two words": "x"})):
            errors.append((f"str-map-{name}-{strict}", "fromDict", {
                "type": "doc", "content": [{"type": "paragraph", "attrs": {"aria": value},
                                            "content": [{"type": "text", "text": "x"}]}],
            }, "str-map", {"strict": strict}))
    for name, operation, value, schema_name, options in errors:
        function = tm.from_dict if operation == "fromDict" else tm.from_markdown
        schema = schemas[schema_name]
        expected = error_result(lambda: function(value, schema=schema, **options))
        payload["errors"].append({
            "id": name, "operation": operation, "value": value, "schema": schema_name,
            "options": js_options(options), "expected": expected,
        })
    schema_results(payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=ROOT / "build-wasm" / "parity.json")
    args = parser.parse_args()
    payload = generate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(payload['documents'])} documents, {len(payload['partial'])} partial inputs, "
          f"{len(payload['errors'])} errors, {len(payload['fingerprints'])} fingerprints, "
          f"{len(payload['presets'])} presets, {len(payload['presetFunctions'])} preset functions, "
          f"{len(payload['schemaCases'])} schemas, {len(payload['extensions'])} extensions and "
          f"{len(payload['schemaErrors'])} schema errors to {args.output}")


if __name__ == "__main__":
    main()
