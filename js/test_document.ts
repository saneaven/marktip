import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { after, test } from "node:test";

import createModule from "./dist/marktip.mjs";
import * as tm from "./dist/marktip.js";

const fixtures = JSON.parse(readFileSync(new URL("../build-wasm/parity.json", import.meta.url), "utf8"));
await tm.init();

function makeSchema(declaration) {
    if (declaration === null) return undefined;
    const { core_attrs, block_image, ...rest } = declaration;
    return new tm.Schema({ ...rest, coreAttrs: core_attrs ?? {}, blockImage: block_image ?? false });
}

const schemas = new Map(Object.entries(fixtures.schemas).map(([name, declaration]) => [name, makeSchema(declaration)]));
after(() => {
    for (const schema of schemas.values()) schema?.free();
});

function optionsFor(fixture) {
    return { ...fixture.options, schema: schemas.get(fixture.schema) };
}

function checkSnapshot(document, expected) {
    assert.deepEqual(document.toDict(), expected.dict);
    assert.deepEqual(document.dump(), expected.dump);
    assert.equal(document.toMarkdown(), expected.markdown);
    assert.equal(document.toMarkdown({ canonical: true }), expected.canonical);
}

test("version and repeated initialization", async () => {
    assert.equal(tm.version, fixtures.version);
    await tm.init();
    assert.equal(tm.version, fixtures.version);
});

test("document equality compares trees and schemas independently of remembered spelling", () => {
    const first = tm.fromMarkdown("*x*");
    const second = tm.fromMarkdown("_x_");
    const differentSchema = tm.fromMarkdown("*x*", { schema: schemas.get("declared") });
    try {
        assert.notEqual(first.toMarkdown(), second.toMarkdown());
        assert.equal(first.equals(second), true);
        assert.deepEqual(first.toDict(), differentSchema.toDict());
        assert.equal(first.equals(differentSchema), false);
        for (const other of [null, undefined, "*x*", first.toDict(), Object.create(tm.Document.prototype)]) {
            assert.equal(first.equals(other), false);
        }
    } finally {
        differentSchema.free();
        second.free();
        first.free();
    }
});

test("document equality ignores mark attr key order", () => {
    const first = tm.fromMarkdown('[x](/docs "Docs")');
    const tree = first.toDict();
    tree.content[0].content[0].marks[0].attrs = { title: "Docs", href: "/docs" };
    const second = tm.fromDict(tree, { strict: "content" });
    try {
        assert.notEqual(JSON.stringify(first.toDict()), JSON.stringify(second.toDict()));
        assert.equal(first.equals(second), true);
    } finally {
        second.free();
        first.free();
    }
});

test("plain object StrMap declarations roundtrip tag attrs as a nested object", () => {
    const schema = new tm.Schema({ nodes: [{
        name: "customDiv", kind: "block", content: "block+", tag: "custom-div",
        attrs: { class: { type: "str" }, data: { type: "StrMap" } },
    }] });
    const source = '<custom-div class="game.status" data-hp="30" data-name="리안">\n\nx\n\n</custom-div>';
    const document = tm.fromMarkdown(source, { schema });
    let restored;
    try {
        const dict = document.toDict();
        assert.deepEqual(dict, { type: "doc", content: [{
            type: "customDiv", attrs: { class: "game.status", data: { hp: "30", name: "리안" } },
            content: [{ type: "paragraph", content: [{ type: "text", text: "x" }] }],
        }] });
        restored = tm.fromDict(dict, { schema, strict: "exact" });
        assert.equal(restored.toMarkdown({ canonical: true }), source);
    } finally {
        restored?.free();
        document.free();
        schema.free();
    }
});

test("strict dict input accepts marks on inline containers and their children", () => {
    const schema = schemas.get("partial");
    const underline = { type: "underline" };
    const tree = { type: "doc", content: [{ type: "paragraph", content: [{
        type: "ruby", marks: [underline], content: [{ type: "text", text: "x", marks: [underline] }],
    }] }] };
    for (const strict of ["content", "exact"]) {
        const document = tm.fromDict(tree, { schema, strict });
        try {
            assert.deepEqual(document.toDict(), tree);
        } finally {
            document.free();
        }
    }
});

test("container code marks use strict validation and are omitted by the off writer", () => {
    const schema = schemas.get("partial");
    const tree = { type: "doc", content: [{ type: "paragraph", content: [{
        type: "ruby", marks: [{ type: "code" }, { type: "underline" }],
        content: [{ type: "text", text: "x" }],
    }] }] };
    for (const strict of ["content", "exact"]) {
        assert.throws(() => tm.fromDict(tree, { schema, strict }), error => {
            assert.ok(error instanceof tm.InvalidNodeError);
            assert.equal(error.code, "invalid_mark_set");
            assert.equal(error.field, "marks");
            assert.equal(error.path, "content[0].content[0]");
            return true;
        });
    }
    const document = tm.fromDict(tree, { schema, strict: "off" });
    try {
        assert.deepEqual(document.toDict(), tree);
        assert.equal(document.toMarkdown({ canonical: true }), "<u><ruby>x</ruby></u>");
    } finally {
        document.free();
    }
});

for (const fixture of fixtures.documents) {
    test(`document parity: ${fixture.id}`, () => {
        const options = optionsFor(fixture);
        const document = tm.fromMarkdown(fixture.markdown, options);
        let loaded;
        let edited;
        try {
            checkSnapshot(document, fixture.expected);
            loaded = tm.load(document.dump(), { schema: options.schema });
            assert.deepEqual(loaded.dump(), fixture.loadedDump);
            assert.equal(loaded.equals(document), fixture.loadedEquals);
            edited = tm.fromDict(fixture.editorInput, {
                schema: options.schema, base: loaded, cjkFriendly: options.cjkFriendly,
            });
            checkSnapshot(edited, fixture.editorExpected);
            assert.equal(edited.equals(document), fixture.editorEquals);
        } finally {
            edited?.free();
            loaded?.free();
            document.free();
        }
    });
}

for (const fixture of fixtures.editorDocuments) {
    test(`editor parity: ${fixture.id}`, () => {
        const options = optionsFor(fixture);
        const base = fixture.baseDump === null ? undefined : tm.load(fixture.baseDump, { schema: options.schema });
        let document;
        try {
            document = tm.fromDict(fixture.value, { ...options, base });
            checkSnapshot(document, fixture.expected);
        } finally {
            document?.free();
            base?.free();
        }
    });
}

for (const fixture of fixtures.partial) {
    test(`partial parity: ${fixture.id}`, () => {
        const document = tm.fromMarkdown(fixture.markdown, optionsFor(fixture));
        try {
            checkSnapshot(document, fixture.expected);
        } finally {
            document.free();
        }
    });
}

for (const fixture of fixtures.fingerprints) {
    test(`fingerprint parity: ${fixture.schema}`, () => {
        const document = tm.fromMarkdown("", { schema: schemas.get(fixture.schema) });
        try {
            assert.equal(document.dump().schema, fixture.expected);
        } finally {
            document.free();
        }
    });
}

for (const fixture of fixtures.errors) {
    test(`error parity: ${fixture.id}`, () => {
        assert.throws(() => tm[fixture.operation](fixture.value, optionsFor(fixture)), error => {
            assert.ok(error instanceof tm.MarktipError);
            assert.ok(error instanceof tm[fixture.expected.name]);
            const actual = Object.fromEntries(Object.keys(fixture.expected).map(key => [key, error[key]]));
            assert.deepEqual(actual, fixture.expected);
            return true;
        });
    });
}

test("error names do not depend on the class name a bundler may change", () => {
    for (const name of ["MarktipError", "UnknownTypeError", "InvalidNodeError", "ParseError"]) {
        class Renamed extends tm[name] {}
        assert.equal(new Renamed("message").name, name);
    }
});

test("documents reject methods after free and tolerate a second free", () => {
    const document = tm.fromMarkdown("text");
    document.free();
    document.free();
    assert.throws(() => document.toDict(), /freed/i);
    assert.throws(() => document.dump(), /freed/i);
    assert.throws(() => document.toMarkdown(), /freed/i);
    assert.throws(() => document.equals(document), /freed/i);
    assert.throws(() => tm.fromDict({ type: "doc" }, { base: document }), /freed/i);
});

test("schemas reject reuse after free and tolerate a second free", () => {
    const schema = new tm.Schema({ marks: [] });
    schema.free();
    schema.free();
    assert.throws(() => tm.fromMarkdown("text", { schema }), /freed/i);
    assert.throws(() => tm.fromDict({ type: "doc" }, { schema }), /freed/i);
});

test("a derived document keeps spelling after its base is freed", () => {
    const source = "\nTitle\n=====\n\n* first\n";
    const base = tm.fromMarkdown(source);
    const derived = tm.fromDict(base.toDict(), { base });
    base.free();
    try {
        assert.equal(derived.toMarkdown(), source);
        assert.deepEqual(derived.toDict().content[0], {
            type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "Title" }],
        });
    } finally {
        derived.free();
    }
});

test("documents keep their schema alive after its handle is freed", () => {
    const schema = makeSchema(fixtures.schemas.declared);
    const source = "<callout tone='note'>\n\nbody\n\n</callout>";
    const document = tm.fromMarkdown(source, { schema });
    schema.free();
    try {
        assert.equal(document.toDict().content[0].type, "callout");
        assert.equal(document.toMarkdown(), source);
        assert.equal(document.dump().schema, fixtures.fingerprints.find(item => item.schema === "declared").expected);
    } finally {
        document.free();
    }
});

test("caller mistakes use TypeError and RangeError", () => {
    assert.throws(() => tm.fromMarkdown("text", { linkRelative: 1 }), TypeError);
    assert.throws(() => tm.fromMarkdown("text", { linkRelative: "never" }), RangeError);
    assert.throws(() => tm.fromMarkdown("text", { linkSchemes: "https" }), TypeError);
    assert.throws(() => tm.fromDict({ type: "doc" }, { strict: 1 }), TypeError);
    assert.throws(() => tm.fromDict({ type: "doc" }, { strict: "never" }), RangeError);
    assert.throws(() => tm.fromDict({ type: "doc" }, { cjkFriendly: 1 }), TypeError);
});

test("schema declarations must be objects", () => {
    assert.throws(() => new tm.Schema(42), TypeError);
    assert.throws(() => new tm.Schema([]), TypeError);
});

test("whole conversion options must be objects", () => {
    assert.throws(() => tm.fromMarkdown("text", null), TypeError);
    assert.throws(() => tm.fromDict({ type: "doc" }, []), TypeError);
    assert.throws(() => tm.load({ marktip: 1, doc: { type: "doc" } }, 42), TypeError);
});

test("writing options must be objects", () => {
    const document = tm.fromMarkdown("text");
    try {
        assert.throws(() => document.toMarkdown([]), TypeError);
    } finally {
        document.free();
    }
});

test("unknown option names identify the key for each document entry point", () => {
    const document = tm.fromMarkdown("text");
    const tree = document.toDict();
    const stored = document.dump();
    const cases = [
        { key: "keep_source", call: () => tm.fromMarkdown("text", { keep_source: false }) },
        { key: "strict", call: () => tm.fromMarkdown("text", { strict: "exact" }) },
        { key: "partial", call: () => tm.fromDict(tree, { partial: true }) },
        { key: "canonical", call: () => tm.load(stored, { canonical: true }) },
        { key: "keepSource", call: () => document.toMarkdown({ keepSource: true }) },
    ];
    try {
        for (const fixture of cases) {
            assert.throws(fixture.call, error => {
                assert.ok(error instanceof TypeError);
                assert.ok(error.message.includes(fixture.key));
                return true;
            });
        }
    } finally {
        document.free();
    }
});

test("boolean and oversized stored versions are unsupported", () => {
    const document = tm.fromMarkdown("text");
    const stored = document.dump();
    document.free();
    for (const version of [true, 1e20]) {
        assert.throws(() => tm.load({ ...stored, marktip: version }), error => {
            assert.ok(error instanceof RangeError);
            assert.equal(error.message, "unsupported marktip version");
            return true;
        });
    }
});

test("oversized scalar attrs are omitted under strict off", () => {
    const ast = { type: "doc", content: [
        { type: "heading", attrs: { level: 1e20 }, content: [{ type: "text", text: "x" }] },
    ] };
    const document = tm.fromDict(ast);
    try {
        assert.deepEqual(document.toDict(), {
            type: "doc", content: [{ type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "x" }] }],
        });
    } finally {
        document.free();
    }
});

test("non-string text uses the host JSON literal", () => {
    for (const value of [[true, null], { message: "quote\" and newline\n" }]) {
        const document = tm.fromDict({ type: "doc", content: [
            { type: "paragraph", content: [{ type: "text", text: value }] },
        ] });
        try {
            assert.equal(document.toDict().content[0].content[0].text, JSON.stringify(value));
        } finally {
            document.free();
        }
    }
});

test("a missing stored scalar becomes a plain Error without breaking later calls", () => {
    const document = tm.fromMarkdown("text");
    const stored = document.dump();
    document.free();
    delete stored.source.items[0].sep;
    assert.throws(() => tm.load(stored), error => {
        assert.equal(error.name, "Error");
        assert.equal(error.constructor, Error);
        assert.ok(error.message.length > 0);
        return true;
    });
    const next = tm.fromMarkdown("next");
    try {
        assert.equal(next.toDict().content[0].content[0].text, "next");
    } finally {
        next.free();
    }
});

test("raw JSON versions distinguish integer spelling from fractions and exponents", async () => {
    const wasm = await createModule();
    const encoder = new TextEncoder();
    const decoder = new TextDecoder();
    for (const version of ["1", "1.0", "1e0", "true", "18446744073709551616"]) {
        const source = `{"marktip":${version},"doc":{"type":"doc","content":[]}}`;
        const bytes = encoder.encode(source);
        const pointer = wasm._malloc(bytes.length);
        let document;
        try {
            wasm.HEAPU8.set(bytes, pointer);
            document = wasm._mt_load(pointer, bytes.length, 0);
            const errorLength = wasm._mt_error_len();
            if (version === "1") {
                assert.ok(document > 0);
                assert.equal(errorLength, 0);
            } else {
                assert.equal(document, 0);
                const errorPointer = wasm._mt_error_ptr();
                const errorBytes = wasm.HEAPU8.subarray(errorPointer, errorPointer + errorLength);
                const error = JSON.parse(decoder.decode(errorBytes));
                assert.equal(error.name, "RangeError");
                assert.equal(error.message, "unsupported marktip version");
            }
        } finally {
            if (document) wasm._mt_document_free(document);
            wasm._free(pointer);
        }
    }
});

const MAX_NODE_DEPTH = 512;

function deepestNode(root) {
    const pending = [{ node: root, depth: 0 }];
    let deepest = 0;
    while (pending.length > 0) {
        const { node, depth } = pending.pop();
        deepest = Math.max(deepest, depth);
        for (const child of node.content ?? []) pending.push({ node: child, depth: depth + 1 });
    }
    return deepest;
}

test("an over-deep dict reports max_depth", () => {
    let node = { type: "paragraph" };
    for (let i = 0; i < MAX_NODE_DEPTH; ++i) node = { type: "blockquote", content: [node] };
    assert.throws(() => tm.fromDict({ type: "doc", content: [node] }), error => {
        assert.ok(error instanceof tm.InvalidNodeError);
        assert.equal(error.code, "max_depth");
        return true;
    });
});

test("all four deepest-accepted shapes convert and leave the instance usable", context => {
    const schema = new tm.Schema({ nodes: [
        { name: "box", kind: "block", content: "block*" },
        { name: "wrap", kind: "inline", content: "inline*" },
    ] });
    const containers = MAX_NODE_DEPTH - 2;
    const listLevels = (MAX_NODE_DEPTH - 2) / 2;
    const list = Array.from({ length: listLevels }, (_, level) => (
        `${"  ".repeat(level)}- ${level === listLevels - 1 ? "x" : ""}\n`
    )).join("");
    const cases = [
        { name: "blockquote", markdown: `${">".repeat(containers)} x`, schema: undefined },
        { name: "nested list", markdown: list, schema: undefined },
        { name: "declared block container", schema,
          markdown: "<box>\n\n".repeat(containers) + "x\n\n" + "</box>\n\n".repeat(containers) },
        { name: "declared inline container", schema,
          markdown: "<wrap>".repeat(containers) + "x" + "</wrap>".repeat(containers) },
    ];
    try {
        for (const fixture of cases) {
            context.diagnostic(`${fixture.name}: exercising node depth ${MAX_NODE_DEPTH}`);
            const parsed = tm.fromMarkdown(fixture.markdown, { schema: fixture.schema });
            let rebuilt;
            try {
                const tree = parsed.toDict();
                assert.equal(deepestNode(tree), MAX_NODE_DEPTH, fixture.name);
                rebuilt = tm.fromDict(tree, { schema: fixture.schema });
                assert.equal(deepestNode(parsed.dump().doc), MAX_NODE_DEPTH, fixture.name);
                assert.equal(deepestNode(rebuilt.dump().doc), MAX_NODE_DEPTH, fixture.name);
                const canonical = parsed.toMarkdown({ canonical: true });
                assert.equal(rebuilt.toMarkdown({ canonical: true }), canonical, fixture.name);
            } finally {
                rebuilt?.free();
                parsed.free();
            }
            const small = tm.fromMarkdown("still usable");
            try {
                assert.equal(small.toDict().content[0].content[0].text, "still usable", fixture.name);
                assert.equal(small.toMarkdown({ canonical: true }), "still usable", fixture.name);
            } finally {
                small.free();
            }
        }
    } finally {
        schema.free();
    }
});
