import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import * as tm from "./dist/marktip.js";

const fixtures = JSON.parse(readFileSync(new URL("../build-wasm/parity.json", import.meta.url), "utf8"));
await tm.init();

function constructorOptions(declaration) {
    const { core_attrs, block_image, ...rest } = declaration;
    if (Object.hasOwn(declaration, "core_attrs")) rest.coreAttrs = core_attrs;
    if (Object.hasOwn(declaration, "block_image")) rest.blockImage = block_image;
    return rest;
}

function fingerprint(schema) {
    const document = tm.fromMarkdown("", { schema });
    try {
        return document.dump().schema;
    } finally {
        document.free();
    }
}

function checkDeclarationError(call, expected) {
    assert.throws(call, error => {
        assert.equal(error.constructor, expected.name === "TypeError" ? TypeError : RangeError);
        assert.equal(error.name, expected.name);
        assert.equal(error.message, expected.message);
        return true;
    });
}

for (const fixture of fixtures.presets) {
    test(`preset constant parity: ${fixture.name}`, () => {
        assert.deepEqual(tm[fixture.name], fixture.expected);
    });
}

for (const fixture of fixtures.presetFunctions) {
    test(`preset function parity: ${fixture.id}`, () => {
        assert.deepEqual(tm[fixture.function](fixture.options), fixture.expected);
    });
}

for (const fixture of fixtures.schemaCases) {
    test(`schema declaration parity: ${fixture.id}`, () => {
        const options = constructorOptions(fixture.declaration);
        const schema = new tm.Schema(options);
        let restored;
        try {
            assert.deepEqual(schema.toDict(), fixture.expected);
            assert.deepEqual(schema.marks, options.marks ?? []);
            assert.deepEqual(schema.nodes, options.nodes ?? []);
            assert.deepEqual(schema.coreAttrs, options.coreAttrs ?? {});
            assert.equal(schema.blockImage, options.blockImage ?? false);
            assert.equal(fingerprint(schema), fixture.fingerprint);
            restored = tm.Schema.fromDict(JSON.parse(JSON.stringify(fixture.declaration)));
            assert.deepEqual(restored.toDict(), fixture.expected);
            assert.equal(restored.equals(schema), true);
            assert.equal(fingerprint(restored), fixture.fingerprint);
        } finally {
            restored?.free();
            schema.free();
        }
    });
}

test("all preset constants build the same schema as Python", () => {
    const schema = new tm.Schema({
        marks: [tm.UNDERLINE, tm.HIGHLIGHT, tm.SUBSCRIPT, tm.SUPERSCRIPT, tm.TEXT_STYLE],
        nodes: [tm.MENTION, ...tm.DETAILS, tm.INLINE_MATH, tm.BLOCK_MATH],
        coreAttrs: { ...tm.TEXT_ALIGN, ...tm.LINK_ATTRS, ...tm.IMAGE_SIZE, ...tm.TABLE_SPANS },
    });
    const expected = fixtures.schemaCases.find(item => item.id === "all-presets");
    try {
        assert.deepEqual(schema.toDict(), expected.expected);
        assert.equal(fingerprint(schema), expected.fingerprint);
    } finally {
        schema.free();
    }
});

for (const fixture of fixtures.extensions) {
    test(`schema extension parity: ${fixture.id}`, () => {
        const base = tm.Schema.fromDict(fixture.base);
        let extended;
        try {
            extended = base.extend(constructorOptions(fixture.addition));
            assert.notEqual(extended, base);
            assert.deepEqual(base.toDict(), fixture.base);
            assert.deepEqual(extended.toDict(), fixture.expected);
            assert.equal(fingerprint(extended), fixture.fingerprint);
        } finally {
            extended?.free();
            base.free();
        }
    });
}

for (const fixture of fixtures.schemaErrors) {
    test(`core declaration error parity: ${fixture.id}`, () => {
        checkDeclarationError(() => new tm.Schema(constructorOptions(fixture.declaration)), fixture.expected);
        checkDeclarationError(() => tm.Schema.fromDict(fixture.declaration), fixture.expected);
        const base = new tm.Schema();
        try {
            checkDeclarationError(() => base.extend(constructorOptions(fixture.declaration)), fixture.expected);
        } finally {
            base.free();
        }
    });
}

test("extending a duplicate core attr reports Python's value error message", () => {
    const fixture = fixtures.duplicateCoreAttr;
    const base = tm.Schema.fromDict(fixture.base);
    try {
        checkDeclarationError(() => base.extend(constructorOptions(fixture.addition)), fixture.expected);
        assert.deepEqual(base.toDict(), fixture.base);
    } finally {
        base.free();
    }
});

test("an undefined core attr is absent when extending equal schemas", () => {
    const a = new tm.Schema({ coreAttrs: { paragraph: { tone: undefined } } });
    const b = tm.Schema.fromDict(a.toDict());
    const tone = { type: "str" };
    let extendedA;
    let extendedB;
    try {
        assert.equal(a.equals(b), true);
        assert.equal(fingerprint(a), fingerprint(b));
        extendedA = a.extend({ coreAttrs: { paragraph: { tone } } });
        extendedB = b.extend({ coreAttrs: { paragraph: { tone } } });
        assert.deepEqual(extendedA.toDict(), {
            marks: [], core_attrs: { paragraph: {
                tone: { type: "str", required: false, choices: null, default: null, uri: null, inherit: false },
            } },
        });
        assert.deepEqual(extendedA.toDict(), extendedB.toDict());
        assert.equal(extendedA.equals(extendedB), true);
        assert.equal(fingerprint(extendedA), fingerprint(extendedB));
        assert.equal(extendedA.coreAttrs.paragraph.tone, tone);
        assert.equal(extendedB.coreAttrs.paragraph.tone, tone);
    } finally {
        extendedA?.free();
        extendedB?.free();
        a.free();
        b.free();
    }
});

test("schema equality compares declarations and preserves attr order", () => {
    const first = new tm.Schema({ marks: [{ name: "note", attrs: { a: { type: "str" }, b: { type: "int" } } }] });
    const equal = new tm.Schema({ marks: [{ name: "note", attrs: { a: { type: "str" }, b: { type: "int" } } }] });
    const changed = new tm.Schema({
        marks: [{ name: "note", tag: "other", attrs: { a: { type: "str" }, b: { type: "int" } } }],
    });
    const reordered = new tm.Schema({
        marks: [{ name: "note", attrs: { b: { type: "int" }, a: { type: "str" } } }],
    });
    try {
        assert.equal(first.equals(equal), true);
        assert.equal(equal.equals(first), true);
        assert.equal(first.equals(changed), false);
        assert.equal(first.equals(reordered), false);
        assert.equal(first.equals({}), false);
    } finally {
        for (const schema of [first, equal, changed, reordered]) schema.free();
    }
});

test("schema equality also preserves mark, node and core owner order", () => {
    const pairs = [
        [{ marks: [{ name: "first" }, { name: "second" }] },
         { marks: [{ name: "second" }, { name: "first" }] }],
        [{ nodes: [{ name: "first", kind: "inline" }, { name: "second", kind: "inline" }] },
         { nodes: [{ name: "second", kind: "inline" }, { name: "first", kind: "inline" }] }],
        [{ coreAttrs: { paragraph: { tone: { type: "str" } }, heading: { tone: { type: "str" } } } },
         { coreAttrs: { heading: { tone: { type: "str" } }, paragraph: { tone: { type: "str" } } } }],
    ];
    for (const [firstOptions, secondOptions] of pairs) {
        const first = new tm.Schema(firstOptions);
        const second = new tm.Schema(secondOptions);
        try {
            assert.equal(first.equals(second), false);
        } finally {
            first.free();
            second.free();
        }
    }
});

test("schema identity is fixed while attr declarations remain live", () => {
    const choices = ["red", "blue"];
    const attrs = { tone: { type: "str", choices, default: "red" } };
    const schema = new tm.Schema({ marks: [{ name: "note", attrs }] });
    const original = tm.Schema.fromDict(schema.toDict());
    choices.push("green");
    attrs.id = { type: "str" };
    let extended;
    let current;
    try {
        assert.equal(schema.equals(original), true);
        assert.deepEqual(schema.toDict().marks[0].attrs.tone.choices, choices);
        assert.ok(Object.hasOwn(schema.toDict().marks[0].attrs, "id"));
        extended = schema.extend();
        current = new tm.Schema({ marks: [{ name: "note", attrs }] });
        assert.equal(extended.equals(current), true);
        assert.equal(extended.equals(schema), false);
    } finally {
        current?.free();
        extended?.free();
        original.free();
        schema.free();
    }
});

test("unknown constructor and extend option names identify the key", () => {
    const schema = new tm.Schema();
    try {
        for (const key of ["core_attrs", "block_image", "unknown"]) {
            for (const call of [() => new tm.Schema({ [key]: {} }), () => schema.extend({ [key]: {} })]) {
                assert.throws(call, error => {
                    assert.ok(error instanceof TypeError);
                    assert.ok(error.message.includes(key));
                    return true;
                });
            }
        }
    } finally {
        schema.free();
    }
});

test("schema methods reject a freed schema", () => {
    const schema = new tm.Schema();
    schema.free();
    schema.free();
    assert.throws(() => schema.toDict(), /freed/i);
    assert.throws(() => schema.extend(), /freed/i);
    assert.throws(() => schema.equals(schema), /freed/i);
});

test("blockImage requires a boolean and extend null inherits the current value", () => {
    for (const blockImage of [null, 0, 1]) {
        assert.throws(() => new tm.Schema({ blockImage }), TypeError);
    }
    const base = new tm.Schema({ blockImage: true });
    let extended;
    try {
        for (const blockImage of [0, 1]) {
            assert.throws(() => base.extend({ blockImage }), TypeError);
        }
        extended = base.extend({ blockImage: null });
        assert.equal(extended.blockImage, true);
        assert.equal(extended.equals(base), true);
    } finally {
        extended?.free();
        base.free();
    }
});

test("schema dicts use the JSON values that reach the core", () => {
    const declaration = {
        marks: [{ name: "note", tag: NaN, attrs: {
            omitted: undefined, count: { type: "int", default: NaN }, tone: { type: "str", choices: Infinity },
        } }],
        core_attrs: { paragraph: undefined },
    };
    const schema = new tm.Schema(constructorOptions(declaration));
    const restored = tm.Schema.fromDict(declaration);
    const expected = tm.Schema.fromDict(JSON.parse(JSON.stringify(declaration)));
    try {
        assert.deepEqual(schema.toDict(), expected.toDict());
        assert.deepEqual(restored.toDict(), expected.toDict());
        assert.equal(schema.equals(expected), true);
    } finally {
        schema.free();
        restored.free();
        expected.free();
    }
});

test("core attr extensions preserve absent keys and let the core reject wrong shapes", () => {
    const schema = new tm.Schema({ coreAttrs: { paragraph: { tone: { type: "str" } } } });
    let extended;
    try {
        extended = schema.extend({ coreAttrs: { paragraph: undefined } });
        assert.deepEqual(extended.toDict(), schema.toDict());
        assert.equal(extended.equals(schema), true);
        for (const coreAttrs of [42, [], { paragraph: null }, { paragraph: [] }]) {
            assert.throws(() => schema.extend({ coreAttrs }), TypeError);
        }
    } finally {
        extended?.free();
        schema.free();
    }
});
