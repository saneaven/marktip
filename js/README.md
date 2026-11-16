# marktip

Markdown to and from Tiptap/ProseMirror JSON, using the same C++ core as the Python package through WebAssembly.
The package includes TypeScript declarations and is built for bundlers and direct ES module use.
Unbundled use needs a runtime that can import JSON modules with `with { type: "json" }`.
The automated tests run on Node.
The package was also run by hand in Firefox 160: bundled with Vite on the main thread and in a module worker, and as direct ES modules.
Other browsers have not been tried.

```ts
import * as tm from "marktip";
await tm.init();

const schema = new tm.Schema({ marks: [tm.UNDERLINE] });
const doc = tm.fromMarkdown("# Hello\n\n<u>world</u>", { schema });
const editorJson = doc.toDict();
const stored = doc.dump();
const markdown = doc.toMarkdown();
doc.free();
schema.free();
```

Use `partial: true` while receiving a stream and `keepSource: false` when source spelling is unnecessary.
Schema declarations, presets, stored documents and conversion rules match the Python API, with camelCase names and one options object.
See the [main README](https://github.com/saneaven/marktip#javascript-package) for build commands, storage and editing, the full API correspondence, errors and limits.
