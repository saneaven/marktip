import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";

import * as tm from "./dist/marktip.js";

const packageUrl = new URL("./", import.meta.url);
const metadata = JSON.parse(readFileSync(new URL("package.json", packageUrl), "utf8"));

test("package entry points and shipped files exist", () => {
    assert.equal(metadata.name, "marktip");
    assert.equal(metadata.type, "module");
    assert.equal(metadata.types, metadata.exports["."].types);
    for (const path of [
        metadata.exports["."].import,
        metadata.exports["."].types,
        ...metadata.files,
        "dist/marktip.mjs",
        "dist/marktip.wasm",
        "dist/presets.json",
    ]) {
        assert.ok(existsSync(new URL(path, packageUrl)), path);
    }
});

test("the built package initializes and converts a document", async () => {
    await tm.init();
    const document = tm.fromMarkdown("**package**");
    try {
        assert.deepEqual(document.toDict(), {
            type: "doc",
            content: [{ type: "paragraph", content: [{ type: "text", text: "package", marks: [{ type: "bold" }] }] }],
        });
        assert.equal(document.toMarkdown({ canonical: true }), "**package**");
        const pyproject = readFileSync(new URL("../pyproject.toml", packageUrl), "utf8");
        assert.equal(tm.version, metadata.version);
        assert.equal(tm.version, /^version = "([^"]+)"$/m.exec(pyproject)?.[1]);
    } finally {
        document.free();
    }
});

test("built modules have no source-checkout paths or import rewrite helper", () => {
    for (const name of readdirSync(new URL("dist/", packageUrl))) {
        if (!/\.(?:m?js|d\.ts)$/.test(name)) continue;
        const text = readFileSync(new URL(`dist/${name}`, packageUrl), "utf8");
        assert.doesNotMatch(text, /build-wasm|python\/marktip|__rewriteRelativeImportExtension/);
    }
});

test("the package copies the shared presets and all license texts", () => {
    for (const [source, destination] of [
        ["python/marktip/presets.json", "presets.json"],
        ["LICENSE", "licenses/marktip-LICENSE"],
        ["third_party/md4c/LICENSE.md", "licenses/md4c-LICENSE.md"],
        ["third_party/md4c/upstream_metadata/Unicode-LICENSE.txt", "licenses/Unicode-LICENSE.txt"],
        ["third_party/yyjson/LICENSE", "licenses/yyjson-LICENSE"],
    ]) {
        assert.deepEqual(
            readFileSync(new URL(`dist/${destination}`, packageUrl)),
            readFileSync(new URL(`../${source}`, packageUrl)),
        );
    }
});
