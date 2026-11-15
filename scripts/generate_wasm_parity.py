"""Write native document results for the wasm parity test."""

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
    add_document("text/leading-bom", "\ufeffHello\n", "default")
    add_document("overlays/tag-forms", '<p textAlign="center">Aligned</p>\n\n'
                 '<a href="/docs" target="_self">Docs</a> '
                 '<img src="logo.png" width="100" height="80"/>', "overlays")

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

    for schema_name in ("default", "empty", "declared", "pinned", "overlays"):
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
        ("bad-tag-attr", "fromMarkdown", '<callout unknown="value">\n\n</callout>', "declared", {}),
        ("relative-link", "fromMarkdown", "[link](/path)", "default", {"link_relative": "reject"}),
        ("rejected-node", "fromMarkdown", "# Title", "default", {"reject_node_types": ["heading"]}),
    ]
    for name, operation, value, schema_name, options in errors:
        function = tm.from_dict if operation == "fromDict" else tm.from_markdown
        schema = schemas[schema_name]
        expected = error_result(lambda: function(value, schema=schema, **options))
        payload["errors"].append({
            "id": name, "operation": operation, "value": value, "schema": schema_name,
            "options": js_options(options), "expected": expected,
        })
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=ROOT / "build-wasm" / "parity.json")
    args = parser.parse_args()
    payload = generate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(payload['documents'])} documents, {len(payload['partial'])} partial inputs, "
          f"{len(payload['errors'])} errors and {len(payload['fingerprints'])} fingerprints to {args.output}")


if __name__ == "__main__":
    main()
