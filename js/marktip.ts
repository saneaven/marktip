import createModule from "./marktip.mjs";
import { declarationToDict, normalizeMark, normalizeNode, normalizeCoreAttrs } from "./declarations.js";
import type { AttrValue, CoreAttrs, MarkSpec, NodeSpec, SchemaDict } from "./declarations.js";
import { optionsObject, optionNames } from "./options.js";

export type { Attr, AttrValue, CoreAttrs, DeclaredValue, MarkSpec, NodeSpec, SchemaDict } from "./declarations.js";
export * from "./presets.js";

type WasmModule = Awaited<ReturnType<typeof createModule>>;

type ErrorFields = {
    code?: string;
    path?: string;
    detail?: string;
    field?: string;
    type?: string;
    kind?: string;
};

type Buffer = { pointer: number; length: number };

export interface SchemaOptions {
    marks?: readonly MarkSpec[];
    nodes?: readonly NodeSpec[];
    coreAttrs?: CoreAttrs | null;
    blockImage?: boolean;
}

export interface SchemaExtendOptions extends Omit<SchemaOptions, "blockImage"> {
    blockImage?: boolean | null;
}

export interface UriOptions {
    linkSchemes?: readonly string[] | null;
    imageSchemes?: readonly string[] | null;
    linkRelative?: "allow" | "path_only" | "reject";
    imageRelative?: "allow" | "path_only" | "reject";
    rejectNodeTypes?: readonly string[] | null;
    schema?: Schema | null;
}

export interface FromMarkdownOptions extends UriOptions {
    cjkFriendly?: boolean;
    html?: boolean;
    partial?: boolean;
    keepSource?: boolean;
}

export interface FromDictOptions extends UriOptions {
    cjkFriendly?: boolean;
    strict?: "off" | "content" | "exact";
    base?: Document | null;
}

export interface LoadOptions {
    schema?: Schema | null;
}

export interface ToMarkdownOptions {
    canonical?: boolean;
}

export interface TiptapMark {
    type: string;
    attrs?: Record<string, AttrValue>;
}

export interface TiptapNode extends TiptapMark {
    text?: string;
    content?: TiptapNode[];
    marks?: TiptapMark[];
}

export interface StoredDocument {
    marktip: number;
    schema: string;
    doc: TiptapNode;
    source?: { head: string; items: { text?: string; sep: string; node?: false }[] };
}

type SchemaDeclaration = {
    marks: readonly MarkSpec[];
    nodes: readonly NodeSpec[];
    coreAttrs: CoreAttrs;
    blockImage: boolean;
    key: string;
};

let wasm: WasmModule | undefined;
let initialization: Promise<void> | undefined;
export let version = "";

const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { ignoreBOM: true });
const schemas = new WeakMap<Schema, number>();
const declarations = new WeakMap<Schema, SchemaDeclaration>();
const documents = new WeakMap<Document, number>();
const schemaFinalizer = new FinalizationRegistry<number>((handle) => { wasm!._mt_schema_free(handle); });
const documentFinalizer = new FinalizationRegistry<number>((handle) => { wasm!._mt_document_free(handle); });

export class MarktipError extends Error {
    // Literal names: a bundler renames classes, and callers read error.name.
    name = "MarktipError";
    code: string;
    path: string;
    detail: string;

    constructor(message: string, fields: ErrorFields = {}) {
        super(message);
        this.code = fields.code ?? "";
        this.path = fields.path ?? "";
        this.detail = fields.detail ?? message;
    }
}

export class UnknownTypeError extends MarktipError {
    name = "UnknownTypeError";
    type: string;
    kind: string;

    constructor(message: string, fields: ErrorFields = {}) {
        super(message, fields);
        this.type = fields.type ?? "";
        this.kind = fields.kind ?? "";
    }
}

export class InvalidNodeError extends MarktipError {
    name = "InvalidNodeError";
    field: string;

    constructor(message: string, fields: ErrorFields = {}) {
        super(message, fields);
        this.field = fields.field ?? "";
    }
}

export class ParseError extends MarktipError {
    name = "ParseError";
}

function runtime(): WasmModule {
    if (!wasm) {
        throw new Error("Call await init() before using marktip.");
    }
    return wasm;
}

function decode(module: WasmModule, pointer: number, length: number): string {
    return decoder.decode(module.HEAPU8.subarray(pointer, pointer + length));
}

function checkError(module: WasmModule): void {
    const length = module._mt_error_len();
    if (length === 0) return;
    const error = JSON.parse(decode(module, module._mt_error_ptr(), length));
    switch (error.name) {
        case "UnknownTypeError": throw new UnknownTypeError(error.message, error);
        case "InvalidNodeError": throw new InvalidNodeError(error.message, error);
        case "ParseError": throw new ParseError(error.message, error);
        case "MarktipError": throw new MarktipError(error.message, error);
        case "TypeError": throw new TypeError(error.message);
        case "RangeError": throw new RangeError(error.message);
        default: throw new Error(error.message);
    }
}

function result(module: WasmModule): string {
    checkError(module);
    return decode(module, module._mt_result_ptr(), module._mt_result_len());
}

function withStrings<T>(values: string[], call: (module: WasmModule, buffers: Buffer[]) => T): T {
    const module = runtime();
    const buffers: Buffer[] = [];
    try {
        for (const value of values) {
            const bytes = encoder.encode(value);
            const pointer = module._malloc(Math.max(1, bytes.length));
            buffers.push({ pointer, length: bytes.length });
            module.HEAPU8.set(bytes, pointer);
        }
        const output = call(module, buffers);
        checkError(module);
        return output;
    } finally {
        for (const buffer of buffers) module._free(buffer.pointer);
    }
}

function json(value: unknown): string {
    const text = JSON.stringify(value);
    if (text === undefined) throw new TypeError("value must be JSON-serializable");
    return text;
}

function schemaHandle(value: unknown): number {
    if (value === undefined || value === null) return 0;
    if (!(value instanceof Schema)) throw new TypeError("schema must be a Schema or null");
    const handle = schemas.get(value)!;
    if (handle === 0) throw new Error("Schema has been freed");
    return handle;
}

function documentHandle(value: unknown): number {
    if (!(value instanceof Document)) throw new TypeError("base must be a Document or null");
    const handle = documents.get(value)!;
    if (handle === 0) throw new Error("Document has been freed");
    return handle;
}

function documentFromHandle(handle: number): Document {
    const document = Object.create(Document.prototype) as Document;
    documents.set(document, handle);
    documentFinalizer.register(document, handle, document);
    return document;
}

function buildSchema(schema: Schema, data: unknown): void {
    const handle = withStrings([json(data)], (module, [input]) => (
        module._mt_schema_new(input.pointer, input.length)
    ));
    schemas.set(schema, handle);
    schemaFinalizer.register(schema, handle, schema);
}

function copyCoreAttrs(coreAttrs: CoreAttrs): CoreAttrs {
    return Object.fromEntries(Object.entries(coreAttrs).filter(([, attrs]) => attrs !== undefined)
        .map(([owner, attrs]) => [owner, Object.fromEntries(
            Object.entries(attrs).filter(([, attr]) => attr !== undefined),
        )]));
}

function extendCoreAttrs(current: CoreAttrs, addition: CoreAttrs): CoreAttrs {
    if (typeof addition !== "object" || Array.isArray(addition)) return addition;
    const owners = Object.entries(addition).filter(([, attrs]) => attrs !== undefined).map(([owner, attrs]) => {
        if (typeof attrs !== "object" || attrs === null || Array.isArray(attrs)) return [owner, attrs];
        const target = current[owner] ?? {};
        const entries = Object.entries(attrs).filter(([, attr]) => attr !== undefined);
        for (const [name] of entries) {
            if (Object.hasOwn(target, name)) throw new RangeError(`duplicate core attr '${owner}.${name}'`);
        }
        return [owner, Object.fromEntries([...Object.entries(target), ...entries])];
    });
    return Object.fromEntries([...Object.entries(current), ...owners]);
}

function rememberDeclaration(schema: Schema, marks: readonly MarkSpec[], nodes: readonly NodeSpec[],
                             coreAttrs: CoreAttrs, blockImage: boolean): void {
    declarations.set(schema, {
        marks: [...marks], nodes: [...nodes], coreAttrs: copyCoreAttrs(coreAttrs), blockImage,
        key: json(declarationToDict(marks, nodes, coreAttrs, blockImage)),
    });
}

export function init(): Promise<void> {
    if (!initialization) {
        initialization = createModule().then((module: WasmModule) => {
            module._mt_version();
            version = result(module);
            wasm = module;
        });
    }
    return initialization!;
}

export class Schema {
    constructor(declaration: SchemaOptions = {}) {
        runtime();
        const settings = optionsObject(declaration, "schema declaration");
        optionNames(settings, ["marks", "nodes", "coreAttrs", "blockImage"]);
        const { marks = [], nodes = [], coreAttrs = {}, blockImage = false } = (
            settings as SchemaOptions
        );
        buildSchema(this, { marks, nodes, core_attrs: coreAttrs ?? {}, block_image: blockImage });
        rememberDeclaration(this, marks, nodes, coreAttrs ?? {}, blockImage);
    }

    get marks(): readonly MarkSpec[] {
        schemaHandle(this);
        return declarations.get(this)!.marks;
    }

    get nodes(): readonly NodeSpec[] {
        schemaHandle(this);
        return declarations.get(this)!.nodes;
    }

    get coreAttrs(): CoreAttrs {
        schemaHandle(this);
        return declarations.get(this)!.coreAttrs;
    }

    get blockImage(): boolean {
        schemaHandle(this);
        return declarations.get(this)!.blockImage;
    }

    toDict(): SchemaDict {
        schemaHandle(this);
        const { marks, nodes, coreAttrs, blockImage } = declarations.get(this)!;
        return declarationToDict(marks, nodes, coreAttrs, blockImage);
    }

    static fromDict(data: SchemaDict): Schema {
        const schema = Object.create(Schema.prototype) as Schema;
        buildSchema(schema, data);
        const wire = JSON.parse(json(data)) as SchemaDict;
        rememberDeclaration(schema, (wire.marks ?? []).map(normalizeMark), (wire.nodes ?? []).map(normalizeNode),
                            normalizeCoreAttrs(wire.core_attrs ?? {}), wire.block_image ?? false);
        return schema;
    }

    extend(options: SchemaExtendOptions = {}): Schema {
        schemaHandle(this);
        const settings = optionsObject(options, "options");
        optionNames(settings, ["marks", "nodes", "coreAttrs", "blockImage"]);
        const { marks = [], nodes = [], coreAttrs = {}, blockImage = null } = settings as SchemaExtendOptions;
        const current = declarations.get(this)!;
        return new Schema({
            marks: [...current.marks, ...marks], nodes: [...current.nodes, ...nodes],
            coreAttrs: extendCoreAttrs(current.coreAttrs, coreAttrs ?? {}),
            blockImage: blockImage ?? current.blockImage,
        });
    }

    equals(other: unknown): boolean {
        schemaHandle(this);
        if (!(other instanceof Schema)) return false;
        schemaHandle(other);
        return declarations.get(this)!.key === declarations.get(other)!.key;
    }

    free(): void {
        const handle = schemas.get(this)!;
        if (handle === 0) return;
        const module = runtime();
        module._mt_schema_free(handle);
        checkError(module);
        schemas.set(this, 0);
        schemaFinalizer.unregister(this);
    }
}

export class Document {
    private constructor() {}

    toDict(): TiptapNode {
        const module = runtime();
        module._mt_to_dict(documentHandle(this));
        return JSON.parse(result(module));
    }

    dump(): StoredDocument {
        const module = runtime();
        module._mt_dump(documentHandle(this));
        return JSON.parse(result(module));
    }

    toMarkdown(options: ToMarkdownOptions = {}): string {
        const settings = optionsObject(options, "options");
        optionNames(settings, ["canonical"]);
        const { canonical = false } = settings;
        if (typeof canonical !== "boolean") throw new TypeError("canonical must be a bool");
        const module = runtime();
        module._mt_to_markdown(documentHandle(this), canonical ? 1 : 0);
        return result(module);
    }

    equals(other: unknown): boolean {
        const handle = documentHandle(this);
        if (!documents.has(other as Document)) return false;
        const module = runtime();
        const equal = module._mt_equals(handle, documentHandle(other));
        checkError(module);
        return equal !== 0;
    }

    free(): void {
        const handle = documents.get(this)!;
        if (handle === 0) return;
        const module = runtime();
        module._mt_document_free(handle);
        checkError(module);
        documents.set(this, 0);
        documentFinalizer.unregister(this);
    }
}

export function fromMarkdown(markdown: string, options: FromMarkdownOptions = {}): Document {
    runtime();
    if (typeof markdown !== "string") throw new TypeError("fromMarkdown() expects a string");
    const { schema, ...wire } = optionsObject(options, "options");
    const selected = schemaHandle(schema);
    const handle = withStrings([markdown, json(wire)], (module, [input, settings]) => (
        module._mt_from_markdown(input.pointer, input.length, settings.pointer, settings.length, selected)
    ));
    return documentFromHandle(handle);
}

export function fromDict(value: unknown, options: FromDictOptions = {}): Document {
    runtime();
    const { schema, base, ...wire } = optionsObject(options, "options");
    const selected = schemaHandle(schema);
    const inherited = base === undefined || base === null ? 0 : documentHandle(base);
    const handle = withStrings([json(value), json(wire)], (module, [input, settings]) => (
        module._mt_from_dict(input.pointer, input.length, settings.pointer, settings.length, selected, inherited)
    ));
    return documentFromHandle(handle);
}

export function load(value: unknown, options: LoadOptions = {}): Document {
    runtime();
    const settings = optionsObject(options, "options");
    optionNames(settings, ["schema"]);
    const selected = schemaHandle(settings.schema);
    const handle = withStrings([json(value)], (module, [input]) => (
        module._mt_load(input.pointer, input.length, selected)
    ));
    return documentFromHandle(handle);
}
